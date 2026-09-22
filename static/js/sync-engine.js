/*
 * Generic sync engine, driving the offline entity stores in offline-db.js
 * against the /api/sync/* endpoints in sync_api.py.
 *
 * Design notes:
 *   - A record's client_uuid is the idempotency key for the whole trip.
 *     It's generated on-device at creation time, so retrying a push after
 *     a dropped connection safely re-upserts the same row instead of
 *     creating a duplicate (requirement: "prevent duplicate records").
 *   - Conflict handling is last-write-wins with a surfaced warning, not a
 *     silent overwrite in either direction: a push includes the
 *     `updated_at` this device last saw for the row (`base_updated_at`);
 *     if the server's current value has moved on since then, the push is
 *     rejected as a conflict and BOTH versions are kept (locally, and in
 *     the server's sync_conflicts table) for a human to resolve, rather
 *     than one silently clobbering the other.
 *   - Failed pushes back off exponentially per record so a single broken
 *     row (e.g. a genuine validation problem) doesn't get hammered every
 *     sync cycle; they're still retried automatically, just less often.
 */
const SyncEngine = (function () {
    // "Online" means the SERVER was verified reachable (connectivity.js), not merely that
    // the phone has a network interface. Without the monitor loaded, fall back to the
    // browser's flag.
    function isOnline() {
        return (typeof Connectivity !== "undefined") ? Connectivity.isOnline() : navigator.onLine;
    }

    // Every call to the server reports what happened to the monitor: a network-level
    // failure makes it re-check right away (so going offline is noticed in seconds), and
    // a genuine JSON answer proves the server is reachable (a captive-portal page doesn't).
    async function netFetch(url, opts) {
        try {
            const res = await fetch(url, opts);
            if (typeof Connectivity !== "undefined" && (res.headers.get("Content-Type") || "").includes("application/json")) Connectivity.reportSuccess();
            return res;
        } catch (e) {
            if (typeof Connectivity !== "undefined") Connectivity.reportFailure();
            throw e;
        }
    }

    const BATCH_SIZE = 50;
    const MAX_BACKOFF_MS = 5 * 60 * 1000;

    function backoffOk(entry) {
        const meta = entry._sync || {};
        if (!meta.attempts) return true;
        const last = meta.last_attempt_at ? new Date(meta.last_attempt_at).getTime() : 0;
        const wait = Math.min(MAX_BACKOFF_MS, 5000 * Math.pow(2, meta.attempts));
        return Date.now() - last > wait;
    }

    function authHeaders(deviceId, deviceSecret) {
        const h = { "Content-Type": "application/json" };
        if (deviceId && deviceSecret) {
            h["X-Device-Id"] = deviceId;
            h["X-Device-Secret"] = deviceSecret;
        }
        return h;
    }

    function stripMeta(record) {
        const { _sync, ...rest } = record;
        return rest;
    }

    // Pulls a full snapshot and seeds the local school database. Called
    // right after enrollment (see offline-auth.js) so the device is
    // usable offline immediately, without waiting for a second visit.
    // Paginated server-side (sync_api.py's PAGE_SIZE) for large schools —
    // this loops until every entity's `cursor` is exhausted rather than
    // asking the server to hand back an unbounded response in one shot.
    async function bootstrap(schoolId, deviceId, deviceSecret) {
        const headers = authHeaders(deviceId, deviceSecret);
        let cursor = null;
        let firstGeneratedAt = null;
        let totalRows = 0;
        const seen = {};            // entity -> Set of client_uuids the server sent
        // Work this device hasn't synced yet must survive a re-download. This
        // matters most after a long stretch offline: enrolling again to renew
        // access must never overwrite weeks of unsynced entries.
        const unsynced = {};        // entity -> Set of client_uuids with local, unsynced changes
        for (const entity of OfflineDB.ENTITY_STORES) {
            unsynced[entity] = new Set();
            for (const st of ["pending", "failed", "conflict"]) {
                for (const r of await OfflineDB.getByStatus(schoolId, entity, st)) unsynced[entity].add(r.client_uuid);
            }
        }
        do {
            const url = "/api/sync/bootstrap" + (cursor ? `?cursor=${encodeURIComponent(cursor)}` : "");
            const res = await netFetch(url, { headers });
            await failIfUnauthorized(schoolId, res);
            if (!res.ok) throw new Error("Could not download offline data for this device.");
            const data = await res.json();
            firstGeneratedAt = firstGeneratedAt || data.generated_at;
            if (data.school) {
                await OfflineDB.setMeta(schoolId, "school_profile", data.school);
                cacheLogo(schoolId, data.school).catch(() => {});
            }
            for (const [entity, rows] of Object.entries(data.entities)) {
                seen[entity] = seen[entity] || new Set();
                const clean = [];
                for (const r of rows) {
                    seen[entity].add(r.client_uuid);
                    if (unsynced[entity] && unsynced[entity].has(r.client_uuid)) await applyServerRow(schoolId, entity, r);
                    else clean.push({ ...r, _sync: { status: "synced", attempts: 0 } });
                }
                await OfflineDB.putRecords(schoolId, entity, clean);
                totalRows += rows.length;
                document.dispatchEvent(new CustomEvent("offline-sync-progress", { detail: { rows: totalRows } }));
            }
            cursor = data.cursor || null;
        } while (cursor);
        // A full snapshot also tells us what is GONE: records deleted online, or
        // that this account can no longer see, are dropped from the device.
        // Only records that are already synced (so the server still has the
        // truth) are ever removed; unsynced work is never touched.
        for (const entity of OfflineDB.ENTITY_STORES) {
            const keep = seen[entity];
            for (const r of await OfflineDB.getAll(schoolId, entity, { includeDeleted: true })) {
                if (r._sync && r._sync.status === "synced" && !(keep && keep.has(r.client_uuid))) {
                    await OfflineDB.deleteRecord(schoolId, entity, r.client_uuid);
                }
            }
        }
        await OfflineDB.setMeta(schoolId, "last_sync_at", firstGeneratedAt);
        await OfflineDB.setMeta(schoolId, "data_window", await currentWindowKey(schoolId));
        await OfflineDB.setMeta(schoolId, "auth_problem", null);
        broadcastStatus(schoolId);
        return { generated_at: firstGeneratedAt, rowCount: totalRows };
    }

    // The server only sends a device the ACTIVE session's scores/comments and the active
    // term's attendance (see sync_api._WINDOWED) — the rest of a school's history would be
    // far too much for a phone. The window is identified by (active session, active term),
    // worked out here from the synced sessions/terms exactly as the server does.
    async function currentWindowKey(schoolId) {
        const sessions = await OfflineDB.getAll(schoolId, "sessions");
        const terms = await OfflineDB.getAll(schoolId, "terms");
        const active = sessions.filter((s) => s.is_active && s.id).map((s) => s.id);
        const all = sessions.filter((s) => s.id).map((s) => s.id);
        const sessionId = active.length ? Math.max(...active) : (all.length ? Math.max(...all) : 0);
        const term = terms.find((t) => t.session_id === sessionId && t.is_active);
        return `${sessionId}:${term ? term.id : "-"}`;
    }

    // Sign-in problems (expired/revoked credential, school suspended, account
    // deactivated) are NOT record failures: nothing the person entered is wrong,
    // so it all stays queued exactly as it is. We remember why, stop hammering
    // the server, and let the screen tell the person what to do.
    class AuthError extends Error {
        constructor(status) { super("auth: " + status); this.status = status; }
    }
    async function failIfUnauthorized(schoolId, res) {
        if (res.status !== 401) return;
        let status = "not_authenticated";
        try { status = (await res.clone().json()).status || status; } catch (e) { /* keep default */ }
        await OfflineDB.setMeta(schoolId, "auth_problem", { status, at: new Date().toISOString() });
        broadcastStatus(schoolId);
        throw new AuthError(status);
    }

    // A record created offline that references another record ALSO
    // created offline (e.g. a brand-new student in a brand-new,
    // not-yet-synced class) can't use a real numeric foreign key yet —
    // the parent doesn't have a server id until it syncs. `pendingRefs`
    // is an optional {field_name: parent_client_uuid} map for exactly
    // that case; the field itself is left unset until pushPending()'s
    // resolution pass fills it in with the parent's real id, once the
    // parent has synced. See "Dependency-safe offline creation" in
    // OFFLINE_ARCHITECTURE.md.
    // Every queued edit carries: a change_id (unique per edit — lets the server
    // recognise a retried push and never apply it twice), the device's own
    // timestamp, and `base_data` — the field values this device last synced,
    // which is what lets the server merge two devices' edits to DIFFERENT
    // fields instead of calling every concurrent edit a conflict.
    function snapshotFields(rec) {
        const out = {};
        for (const [k, v] of Object.entries(rec)) {
            if (k.startsWith("_") || k === "is_deleted") continue;
            out[k] = v;
        }
        return out;
    }

    // True when every data field of `row` (the server's copy) already equals
    // the local record's value (numbers compared as numbers, blank == null).
    function sameValues(local, row) {
        for (const [k, v] of Object.entries(row)) {
            if (k.startsWith("_") || k === "updated_at" || k === "id" || k === "is_deleted" || k === "client_uuid") continue;
            const a = local[k];
            const blank = (x) => x === null || x === undefined || x === "";
            if (blank(a) && blank(v)) continue;
            if (blank(a) !== blank(v)) {
                if (Number(a) === 0 && Number(v) === 0) continue;
                return false;
            }
            const na = Number(a), nv = Number(v);
            if (Number.isFinite(na) && Number.isFinite(nv) && a !== "" && v !== "") { if (na !== nv) return false; }
            else if (String(a) !== String(v)) return false;
        }
        return true;
    }

    async function queueChange(schoolId, entity, op, data, clientUuid, pendingRefs) {
        let record;
        const changeMeta = () => ({ change_id: crypto.randomUUID(), client_ts: new Date().toISOString() });
        if (op === "create") {
            clientUuid = clientUuid || crypto.randomUUID();
            record = {
                ...data, client_uuid: clientUuid, is_deleted: 0,
                updated_at: new Date().toISOString(),
                _sync: { status: "pending", op: "upsert", base_updated_at: null, base_data: null, attempts: 0, ...changeMeta() },
            };
        } else {
            const existing = await OfflineDB.getRecord(schoolId, entity, clientUuid);
            if (!existing) throw new Error("Record not found locally.");
            // If this row already has an unsynced edit queued, keep the
            // ORIGINAL base_updated_at (the last value the server
            // confirmed) rather than overwriting it with the intermediate
            // local edit — otherwise a conflict on the server side could
            // go undetected.
            const stillPending = existing._sync && existing._sync.status === "pending";
            const baseUpdatedAt = stillPending ? existing._sync.base_updated_at : existing.updated_at;
            const baseData = stillPending ? (existing._sync.base_data || null) : snapshotFields(existing);
            record = {
                ...existing, ...data, client_uuid: clientUuid,
                is_deleted: op === "delete" ? 1 : 0,
                updated_at: new Date().toISOString(),
                _sync: { status: "pending", op: op === "delete" ? "delete" : "upsert", base_updated_at: baseUpdatedAt, base_data: baseData, attempts: 0, ...changeMeta() },
            };
        }
        const owner = currentUserId();
        if (owner) record._owner_user_id = owner; else delete record._owner_user_id;
        if (pendingRefs && Object.keys(pendingRefs).length) {
            record._pending_refs = pendingRefs;
        } else {
            delete record._pending_refs;
        }
        await OfflineDB.putRecord(schoolId, entity, record);
        broadcastStatus(schoolId);
        if (isOnline()) syncNow(schoolId, deviceIdFor(schoolId), deviceSecretFor(schoolId)).catch(() => {});
        return record;
    }

    // These two helpers exist so pages that already have an OfflineAuth
    // session don't have to thread device_id/device_secret through every
    // call site manually.
    function deviceIdFor() { const s = OfflineAuth.getSession(); return s ? s.device_id : null; }
    // Several staff can share one device (one local database per school). A
    // change is pushed under the credentials of whoever MADE it, never under
    // someone else's — otherwise a teacher's edits could be sent, and permission
    // checked and audited, as if an admin who happened to sign in later had made them.
    function currentUserId() {
        try { const s = OfflineAuth.getSession(); return s && s.user ? s.user.user_id : null; } catch (e) { return null; }
    }
    function deviceSecretFor() { const s = OfflineAuth.getSession(); return s ? s.device_secret : null; }

    async function readLocal(schoolId, entity) {
        return OfflineDB.getAll(schoolId, entity);
    }

    // queueChange() fires an opportunistic sync after every single local
    // write, and the 60s auto-sync timer + the 'online' event can all
    // land at once too. This flag makes concurrent callers await the
    // Keep the school logo as a data: URL so printed result sheets show it
    // with no connection. Best effort — a missing logo never blocks a sync.
    async function cacheLogo(schoolId, school) {
        if (!school || !school.logo_url) return;
        const res = await fetch(school.logo_url);
        if (!res.ok) return;
        const blob = await res.blob();
        if (blob.size > 600 * 1024) return;
        const dataUrl = await new Promise((resolve, reject) => {
            const fr = new FileReader();
            fr.onload = () => resolve(fr.result);
            fr.onerror = reject;
            fr.readAsDataURL(blob);
        });
        await OfflineDB.setMeta(schoolId, "school_logo", dataUrl);
    }

    // SAME in-flight sync instead of two syncs stepping on each other.
    let syncInFlight = null;
    // Keep the last-seen notices on the device so the inbox opens with no connection.
    // Best effort: a failure here never affects the sync itself.
    async function refreshNotifications(schoolId, headers) {
        try {
            const res = await netFetch("/api/sync/notifications", { headers });
            if (res.ok) await OfflineDB.setMeta(schoolId, "notifications", { ...(await res.json()), fetched_at: new Date().toISOString() });
        } catch (e) { /* offline or server hiccup: keep what we have */ }
    }

    // First run on a device (or after its local data was cleared) needs a full
    // download; every later run is an incremental sync.
    async function ensureReady(schoolId, deviceId, deviceSecret) {
        if (!isOnline() || !schoolId) return { skipped: true };
        const last = await OfflineDB.getMeta(schoolId, "last_sync_at");
        if (!last) {
            try { return { bootstrap: await bootstrap(schoolId, deviceId, deviceSecret) }; }
            catch (e) { if (e instanceof AuthError) return { authError: e.status }; throw e; }
        }
        return syncNow(schoolId, deviceId, deviceSecret);
    }

    async function syncNow(schoolId, deviceId, deviceSecret) {
        if (!isOnline() || !schoolId) return { skipped: true };
        // A change made WHILE a sync is already running isn't part of it (the run
        // has already read what to push), so remember to go round again right after.
        if (syncInFlight) { rerunRequested = true; return syncInFlight; }
        syncInFlight = (async () => {
            const headers = authHeaders(deviceId, deviceSecret);
            syncingNow = true;
            broadcastStatus(schoolId);
            try {
                const pushResult = await pushPending(schoolId, headers);
                const actionResult = await pushActions(schoolId, headers);
                let pullResult = await pullDeltas(schoolId, headers);
                // The school moved to a new term/session: download the new window (this also
                // drops the old one from the device, but never anything not yet synced).
                const windowNow = await currentWindowKey(schoolId);
                const windowThen = await OfflineDB.getMeta(schoolId, "data_window");
                if (!windowThen) await OfflineDB.setMeta(schoolId, "data_window", windowNow);
                else if (windowThen !== windowNow) pullResult = { ...pullResult, rebootstrap: await bootstrap(schoolId, deviceId, deviceSecret) };
                if (await OfflineDB.getMeta(schoolId, "auth_problem")) await OfflineDB.setMeta(schoolId, "auth_problem", null);
                await refreshNotifications(schoolId, headers);
                broadcastStatus(schoolId);
                return { push: pushResult, actions: actionResult, pull: pullResult };
            } catch (e) {
                if (e instanceof AuthError) return { authError: e.status };
                throw e;
            } finally {
                syncingNow = false;
                broadcastStatus(schoolId);
            }
        })();
        let result;
        try {
            result = await syncInFlight;
        } finally {
            syncInFlight = null;
        }
        if (rerunRequested) {
            rerunRequested = false;
            syncNow(schoolId, deviceId, deviceSecret).catch(() => {});
        }
        return result;
    }

    // Queues a request for something that can only actually happen with a
    // live internet connection (e.g. emailing results — see
    // DEFERRED_ACTION_TYPES in app.py). Unlike queueChange(), there's
    // nothing to show locally in the meantime: this is a command, not
    // data, so it just waits here until the next successful sync actually
    // runs it server-side.
    async function queueAction(schoolId, actionType, payload) {
        const clientUuid = crypto.randomUUID();
        const record = {
            client_uuid: clientUuid, action_type: actionType, payload,
            queued_at: new Date().toISOString(),
            _sync: { status: "pending", attempts: 0 },
        };
        await OfflineDB.putRecord(schoolId, "actions", record);
        broadcastStatus(schoolId);
        if (isOnline()) syncNow(schoolId, deviceIdFor(), deviceSecretFor()).catch(() => {});
        return record;
    }

    async function pushActions(schoolId, headers) {
        const pending = (await OfflineDB.getByStatus(schoolId, "actions", "pending"))
            .concat(await OfflineDB.getByStatus(schoolId, "actions", "failed"))
            .filter(backoffOk);
        if (!pending.length) return { done: 0, failed: 0 };
        const byUuid = {};
        const actions = pending.map((r) => {
            byUuid[r.client_uuid] = r;
            return { client_uuid: r.client_uuid, action_type: r.action_type, payload: r.payload };
        });
        let res;
        try {
            res = await netFetch("/api/actions/queue", { method: "POST", headers, body: JSON.stringify({ actions }) });
        } catch (e) {
            return { done: 0, failed: 0 }; // stays pending, retried next cycle
        }
        await failIfUnauthorized(schoolId, res);
        if (!res.ok) return { done: 0, failed: 0 };
        const data = await res.json();
        let done = 0, failed = 0;
        for (const result of data.results) {
            const record = byUuid[result.client_uuid];
            if (!record) continue;
            if (result.status === "done") {
                record._sync = { status: "synced", attempts: 0, result_message: result.message };
                done++;
            } else {
                record._sync = {
                    status: "failed", attempts: (record._sync.attempts || 0) + 1,
                    last_attempt_at: new Date().toISOString(), last_error: result.message,
                };
                failed++;
            }
            await OfflineDB.putRecord(schoolId, "actions", record);
        }
        return { done, failed };
    }

    // Entities are pushed in dependency tiers so a record created offline
    // that depends on ANOTHER record also created offline (new student in
    // a new class; new score for a new student) gets its foreign key
    // resolved to a real server id as soon as the parent syncs — within
    // the SAME sync pass, not next time. Tier order mirrors the actual FK
    // graph: classes/subjects/users have no dependencies on offline data;
    // students depend on classes/users; everything else depends on
    // students (+ subjects, already tier 1).
    const SYNC_TIERS = [
        ["classes", "subjects", "users", "grading_config", "grade_scale"],
        ["students", "class_subjects"],
        ["scores", "attendance_records", "student_term_info", "staff_attendance"],
    ];

    // Fills in any `_pending_refs` on `record` whose parent has since
    // synced (i.e. now has a real numeric `id`). Returns true if the
    // record has no unresolved refs left (so it's safe to push).
    async function resolveRefs(schoolId, entity, record) {
        if (!record._pending_refs || !Object.keys(record._pending_refs).length) return true;
        const remaining = {};
        for (const [field, parentInfo] of Object.entries(record._pending_refs)) {
            const [parentEntity, parentUuid] = parentInfo.split(":");
            const parent = await OfflineDB.getRecord(schoolId, parentEntity, parentUuid);
            if (parent && parent.id) {
                record[field] = parent.id;
            } else if (parent && parent._sync && parent._sync.status === "conflict") {
                // The parent itself is stuck on a conflict — surface this
                // record as blocked too rather than silently waiting
                // forever with no explanation.
                record._sync.last_error = `Waiting on a ${parentEntity} record that has a sync conflict — resolve that first.`;
                remaining[field] = parentInfo;
            } else {
                remaining[field] = parentInfo;
            }
        }
        if (Object.keys(remaining).length) {
            record._pending_refs = remaining;
            await OfflineDB.putRecord(schoolId, entity, record);
            return false;
        }
        delete record._pending_refs;
        return true;
    }

    async function pushPending(schoolId, headers) {
        let totalSynced = 0, totalConflicts = 0, totalErrors = 0, totalBlocked = 0, totalOthers = 0;
        for (const tier of SYNC_TIERS) {
            const changes = [];
            const byUuid = {};
            for (const entity of tier) {
                // "failed" means the server looked at the change and refused it (a
                // rule, or the record it belongs to is gone). Trying again
                // automatically only fills the audit trail with the same refusal,
                // so it is retried a few times (in case something changed) and
                // then left for the person to correct, retry or discard.
                const pending = (await OfflineDB.getByStatus(schoolId, entity, "pending"))
                    .concat((await OfflineDB.getByStatus(schoolId, entity, "failed")).filter((r) => (r._sync.attempts || 0) < 3))
                    .filter(backoffOk);
                const me = currentUserId();
                for (const record of pending) {
                    if (me && record._owner_user_id && record._owner_user_id !== me) { totalOthers++; continue; }
                    const ready = await resolveRefs(schoolId, entity, record);
                    if (!ready) { totalBlocked++; continue; }
                    if (!record._sync.change_id) record._sync.change_id = crypto.randomUUID();
                    changes.push({
                        entity, client_uuid: record.client_uuid,
                        change_id: record._sync.change_id,
                        client_ts: record._sync.client_ts || record.updated_at,
                        op: record._sync.op === "delete" ? "delete" : "upsert",
                        base_updated_at: record._sync.base_updated_at,
                        base_data: record._sync.base_data || null,
                        data: stripMeta(record),
                    });
                    byUuid[record.client_uuid] = { entity, record };
                }
            }
            if (!changes.length) continue;
            const result = await pushBatch(schoolId, headers, changes, byUuid);
            totalSynced += result.synced;
            totalConflicts += result.conflicts;
            totalErrors += result.errors;
            // Tier boundary: records in the NEXT tier that reference
            // something just synced in THIS tier get resolved before we
            // move on, so e.g. a student created in the same offline
            // session as its class doesn't have to wait for a second
            // sync cycle.
        }
        return { synced: totalSynced, conflicts: totalConflicts, errors: totalErrors, blocked: totalBlocked, waitingForOtherUsers: totalOthers };
    }

    async function pushBatch(schoolId, headers, changes, byUuid) {
        let synced = 0, conflicts = 0, errors = 0;
        for (let i = 0; i < changes.length; i += BATCH_SIZE) {
            const batch = changes.slice(i, i + BATCH_SIZE);
            let res;
            try {
                res = await netFetch("/api/sync/push", { method: "POST", headers, body: JSON.stringify({ changes: batch }) });
            } catch (e) {
                break; // connection dropped mid-sync; whatever's left stays pending for next time
            }
            await failIfUnauthorized(schoolId, res);
            if (!res.ok) break;
            const data = await res.json();
            for (const result of data.results) {
                const ref = byUuid[result.client_uuid];
                if (!ref) continue;
                const { entity, record } = ref;
                if (result.status === "synced") {
                    // The server may have combined this edit with another
                    // device's (outcome "merged"), or kept a more recent edit
                    // instead of this one ("latest_wins"). Either way the
                    // server's row is now the truth, so adopt it.
                    const oldUuid = record.client_uuid;
                    if (result.server_data) Object.assign(record, result.server_data);
                    record.id = result.server_id;
                    record.updated_at = result.updated_at;
                    record._sync = { status: "synced", attempts: 0 };
                    if (result.outcome === "merged" || result.outcome === "latest_wins") {
                        record._sync.outcome = result.outcome;
                        record._sync.note = result.message || null;
                        record._sync.at = new Date().toISOString();
                    }
                    // A password only ever needs to reach the server once
                    // (it's hashed there — see _hash_password_before_write
                    // in sync_api.py) — don't leave the plaintext sitting
                    // around locally any longer than it takes to sync.
                    delete record.password;
                    delete record.password_hash;
                    delete record._owner_user_id;
                    // Two devices created the same cell (same student+subject+term)
                    // offline: the server keeps ONE row. Re-key ours onto it.
                    if (result.canonical_client_uuid && result.canonical_client_uuid !== oldUuid) {
                        await OfflineDB.deleteRecord(schoolId, entity, oldUuid);
                        record.client_uuid = result.canonical_client_uuid;
                    }
                    synced++;
                } else if (result.status === "conflict") {
                    record._sync = {
                        status: "conflict", op: record._sync.op,
                        base_updated_at: record._sync.base_updated_at,
                        base_data: record._sync.base_data || null,
                        change_id: record._sync.change_id, client_ts: record._sync.client_ts,
                        server_data: result.server_data || null,
                        conflicting_fields: result.conflicting_fields || [],
                        attempts: (record._sync.attempts || 0) + 1,
                        last_attempt_at: new Date().toISOString(),
                        last_error: result.message,
                    };
                    conflicts++;
                } else {
                    record._sync = {
                        ...record._sync,
                        status: "failed",
                        attempts: (record._sync.attempts || 0) + 1,
                        last_attempt_at: new Date().toISOString(),
                        last_error: result.message,
                    };
                    errors++;
                }
                await OfflineDB.putRecord(schoolId, entity, record);
            }
        }
        return { synced, conflicts, errors };
    }

    // Applies ONE row received from the server to this device's copy. Shared by
    // pull and bootstrap, so a full re-download can never do what an incremental
    // pull wouldn't: overwrite work this device hasn't synced yet.
    // Returns true when the local copy changed.
    async function applyServerRow(schoolId, entity, row) {
        const local = await OfflineDB.getRecord(schoolId, entity, row.client_uuid);
        const st = local && local._sync && local._sync.status;
        if (st === "pending" || st === "conflict" || st === "failed") {
            // The server sends a few seconds of overlap on every pull, so it
            // will often hand back the very version this device already
            // started from. That isn't a change by anyone else — ignore it.
            const known = st === "conflict"
                ? (local._sync.server_data && local._sync.server_data.updated_at)
                : local._sync.base_updated_at;
            if (known && row.updated_at === known) return false;
            // A push whose reply was lost (dropped connection) has still been
            // applied by the server. When the row already holds exactly what
            // this device queued, the change has landed: mark it synced rather
            // than reporting a "conflict" with ourselves.
            if (st === "pending" && sameValues(local, row)) {
                await OfflineDB.putRecord(schoolId, entity, { ...row, _sync: { status: "synced", attempts: 0 } });
                return true;
            }
            // Never clobber an unsynced local edit with an incoming server
            // change. What happens next depends on where the edit is:
            //  - waiting to be pushed (pending/failed): leave it alone. The
            //    server compares versions when it receives the push and either
            //    combines the two edits (different fields) or reports a real
            //    conflict, so flagging one here would only create false alarms;
            //  - already flagged as a conflict: remember the server's newest
            //    copy so "keep server's" restores the latest one.
            if (st === "conflict") {
                local._sync = { ...local._sync, server_data: row };
                await OfflineDB.putRecord(schoolId, entity, local);
                return true;
            }
            return false;
        }
        // Overlap can also re-send a row older than what we already hold
        // (e.g. after a merge) — never go backwards.
        if (local && local.updated_at && row.updated_at && local.updated_at > row.updated_at) return false;
        await OfflineDB.putRecord(schoolId, entity, { ...row, _sync: { status: "synced", attempts: 0 } });
        return true;
    }

    async function pullDeltas(schoolId, headers) {
        const since = await OfflineDB.getMeta(schoolId, "last_sync_at");
        let cursor = null;
        let firstGeneratedAt = null;
        let applied = 0;
        do {
            let url = "/api/sync/pull" + (since ? `?since=${encodeURIComponent(since)}` : "");
            url += (since ? "&" : "?") + (cursor ? `cursor=${encodeURIComponent(cursor)}` : "");
            const res = await netFetch(url, { headers });
            await failIfUnauthorized(schoolId, res);
            if (!res.ok) break;
            const data = await res.json();
            firstGeneratedAt = firstGeneratedAt || data.generated_at;
            if (data.school) await OfflineDB.setMeta(schoolId, "school_profile", data.school);
            for (const [entity, rows] of Object.entries(data.entities)) {
                for (const row of rows) {
                    if (await applyServerRow(schoolId, entity, row)) applied++;
                }
            }
            // Records deleted online (the online screens hard-delete): drop
            // them here too, unless this device has unsynced work on one —
            // then keep it and flag it, so that work isn't silently lost.
            for (const gone of (data.deleted || [])) {
                const local = await OfflineDB.getRecord(schoolId, gone.entity, gone.client_uuid);
                if (!local) continue;
                if (local._sync && (local._sync.status === "pending" || local._sync.status === "conflict")) {
                    local._sync = { ...local._sync, status: "conflict", server_data: null,
                        last_error: "This record was deleted online while you had unsynced changes to it." };
                    await OfflineDB.putRecord(schoolId, gone.entity, local);
                } else {
                    await OfflineDB.deleteRecord(schoolId, gone.entity, gone.client_uuid);
                }
                applied++;
            }
            cursor = data.cursor || null;
        } while (cursor);
        // Using the FIRST page's timestamp (not the last) as the new
        // watermark is deliberate: a record changed on the server while
        // this multi-page pull was still in progress will simply be
        // fetched again next time (its updated_at will be > this value),
        // which is redundant but never lossy. Using the last page's
        // timestamp instead could skip a record that changed in the gap
        // between pages.
        if (firstGeneratedAt) await OfflineDB.setMeta(schoolId, "last_sync_at", firstGeneratedAt);
        return { applied };
    }

    // Throws away one local, unsynced change. A record that was never on the
    // server disappears; one that was goes back to how it was before the edit.
    async function discardChange(schoolId, entity, clientUuid) {
        const record = await OfflineDB.getRecord(schoolId, entity, clientUuid);
        if (!record || !record._sync || record._sync.status === "synced") return;
        if (!record.id) {
            await OfflineDB.deleteRecord(schoolId, entity, clientUuid);
        } else {
            const base = record._sync.base_data || (record._sync.server_data ? snapshotFields(record._sync.server_data) : null);
            if (base) {
                const restored = { ...record, ...base, updated_at: record._sync.base_updated_at || base.updated_at || record.updated_at, is_deleted: 0, _sync: { status: "synced", attempts: 0 } };
                delete restored._owner_user_id; delete restored._pending_refs;
                await OfflineDB.putRecord(schoolId, entity, restored);
            } else {
                await OfflineDB.deleteRecord(schoolId, entity, clientUuid);   // nothing to restore from; the next sync brings the server's copy back
            }
        }
        broadcastStatus(schoolId);
    }

    async function resolveConflict(schoolId, entity, clientUuid, keepLocal) {
        const record = await OfflineDB.getRecord(schoolId, entity, clientUuid);
        if (!record) return;
        const server = record._sync.server_data || null;
        // A clash on the same student+subject+term cell comes back with the
        // server's row under a DIFFERENT client_uuid. Resolving means folding
        // this record onto that row.
        const sameCell = server && server.client_uuid && server.client_uuid !== record.client_uuid;
        if (keepLocal) {
            const next = {
                ...record,
                _sync: {
                    status: "pending", op: record._sync.op || "upsert",
                    base_updated_at: server ? server.updated_at : null,
                    base_data: server ? snapshotFields(server) : null,
                    attempts: 0, change_id: crypto.randomUUID(), client_ts: new Date().toISOString(),
                },
            };
            if (sameCell) {
                await OfflineDB.deleteRecord(schoolId, entity, record.client_uuid);
                next.client_uuid = server.client_uuid;
                next.id = server.id;
            }
            await OfflineDB.putRecord(schoolId, entity, next);
        } else if (server) {
            if (sameCell) await OfflineDB.deleteRecord(schoolId, entity, record.client_uuid);
            await OfflineDB.putRecord(schoolId, entity, { ...server, _sync: { status: "synced", attempts: 0 } });
        } else {
            // The record was deleted online; keeping "the server's version" means it's gone.
            await OfflineDB.deleteRecord(schoolId, entity, record.client_uuid);
        }
        broadcastStatus(schoolId);
    }

    let syncingNow = false;
    let rerunRequested = false;
    async function broadcastStatus(schoolId) {
        const counts = await OfflineDB.getPendingCounts(schoolId);
        const lastSync = await OfflineDB.getMeta(schoolId, "last_sync_at");
        document.dispatchEvent(new CustomEvent("offline-sync-status", {
            detail: { ...counts, online: isOnline(), lastSync, syncing: syncingNow },
        }));
    }

    let autoTimer = null;
    let offConnectivity = null;
    function startAutoSync(schoolId) {
        stopAutoSync();
        // A sync can fail for a moment even though the server is reachable (it may have
        // only just come back). If changes are still waiting and nothing got through, try
        // again shortly — 5s, 10s, 20s … up to a minute — instead of waiting for the next timer.
        let retryDelay = 5000, retryTimer = null;
        const trigger = () => {
            if (retryTimer) { clearTimeout(retryTimer); retryTimer = null; }
            return syncNow(schoolId, deviceIdFor(), deviceSecretFor()).then(async (r) => {
                const progressed = r && r.push && (r.push.synced || r.push.conflicts || r.push.errors);
                const counts = await OfflineDB.getPendingCounts(schoolId);
                const others = r && r.push ? (r.push.waitingForOtherUsers || 0) : 0;
                if (r && !r.authError && isOnline() && counts.pending - others > 0 && !progressed) {
                    retryTimer = setTimeout(trigger, retryDelay);
                    retryDelay = Math.min(retryDelay * 2, 60000);
                } else retryDelay = 5000;
            }).catch((e) => {
                console.warn("sync failed", e);
                if (isOnline()) { retryTimer = setTimeout(trigger, retryDelay); retryDelay = Math.min(retryDelay * 2, 60000); }
            });
        };
        if (typeof Connectivity !== "undefined") {
            // The moment the server is VERIFIED reachable again, sync in the background.
            offConnectivity = Connectivity.onChange((on) => { if (on) trigger(); broadcastStatus(schoolId); });
        } else {
            window.addEventListener("online", trigger);
        }
        autoTimer = setInterval(() => { if (isOnline()) trigger(); }, 60000);
        if (isOnline()) trigger();
    }
    function stopAutoSync() {
        if (autoTimer) clearInterval(autoTimer);
        autoTimer = null;
        if (offConnectivity) { offConnectivity(); offConnectivity = null; }
    }

    return {
        bootstrap, ensureReady, queueChange, queueAction, readLocal, syncNow, resolveConflict, discardChange,
        broadcastStatus, startAutoSync, stopAutoSync,
    };
})();
