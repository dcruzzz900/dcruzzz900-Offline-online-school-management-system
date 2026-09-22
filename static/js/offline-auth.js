/*
 * Offline authentication.
 *
 * Flow:
 *   1. ENROLL (must be online): every time someone logs in online, the login
 *      page calls provisionAfterLogin() while their password is still in
 *      memory. It asks the server for a fresh offline credential
 *      (/api/offline/enroll — for a returning person on this device the SAME
 *      device id, so nothing they have queued is disturbed) and encrypts it
 *      with THEIR PASSWORD. So the offline password is simply their normal
 *      password; there is no separate PIN to set up or forget. If they later
 *      change their password, their next online login re-wraps it. The
 *      plaintext credential is never written to disk. (enroll() with any other
 *      secret, e.g. an admin-chosen PIN, still works for special cases.)
 *   2. UNLOCK (works with zero connectivity): the staff member enters their
 *      password (the offline app skips the account list when the device only
 *      has one account). If it
 *      decrypts successfully, an in-memory + sessionStorage "offline
 *      session" is created — this is what every offline page checks
 *      before showing anything.
 *   3. Offline session expiry: two independent limits, matching the
 *      "offline-session expiry and security controls" requirement —
 *        - a SHORT one (OFFLINE_SESSION_MAX_HOURS): the unlocked session
 *          expires after a few hours OR whenever the browser/tab is fully
 *          closed (sessionStorage doesn't survive that), whichever is
 *          sooner — so an unattended unlocked device doesn't stay usable
 *          indefinitely;
 *        - a LONG one (server-side, see db.py's OFFLINE_CREDENTIAL_LIFETIME_DAYS):
 *          the credential itself stops working after ~3 weeks with no
 *          successful online re-verification, so a device that's lost or
 *          a staff member who has left can't use it forever even if they
 *          remember the PIN.
 *   4. On reconnect, verifyOnline() re-checks the credential against the
 *      server (revoked? school suspended? expired?) and slides the long
 *      expiry forward.
 */
const OfflineAuth = (function () {
    const SESSION_KEY = "srs_offline_session";
    const MAX_SESSION_HOURS = 12;

    async function csrfHeader() {
        const res = await fetch("/csrf-token", { credentials: "same-origin" });
        if (!res.ok) throw new Error("Not logged in online — open the app normally first.");
        const data = await res.json();
        return data.csrf_token;
    }

    // Step 1 — must be called while online, from a normal logged-in page.
    // `secret` is what will unlock the credential offline: the person's
    // password (see provisionAfterLogin) or, on the legacy settings screen, a PIN.
    // opts.deviceId  : renew THIS device's existing credential (same id, new secret)
    // opts.bootstrap : also download the school's data now (default true)
    async function enroll(secret, deviceLabel, opts) {
        opts = opts || {};
        const csrf = await csrfHeader();
        const res = await fetch("/api/offline/enroll", {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
            body: JSON.stringify({ device_label: deviceLabel || navigator.userAgent.slice(0, 40), device_id: opts.deviceId || undefined }),
        });
        if (!res.ok) throw new Error("Could not enroll this device for offline access.");
        const data = await res.json();
        const encrypted = await OfflineCrypto.encrypt(secret, {
            device_id: data.device_id,
            device_secret: data.device_secret,
            user: data.user,
        });
        // One entry per person per school on this device: if the server issued a
        // different device id (it never re-uses another person's), drop the stale one.
        for (const a of await OfflineDB.listAccounts()) {
            if (a.device_id !== data.device_id && a.school_id === data.user.school_id
                && a.user_id && a.user_id === data.user.user_id) {
                await OfflineDB.deleteAccount(a.device_id);
            }
        }
        await OfflineDB.saveAccount({
            device_id: data.device_id,
            encrypted,
            label: `${data.user.name} — ${data.user.role.replace("_", " ")}`,
            username: data.user.username || null,
            user_id: data.user.user_id,
            school_id: data.user.school_id,
            enrolled_at: new Date().toISOString(),
            expires_at: data.expires_at,
        });
        if (opts.bootstrap !== false) {
            // Seed the local database immediately so this device works offline
            // even if it never gets a second online moment before connectivity is lost.
            await SyncEngine.bootstrap(data.user.school_id, data.device_id, data.device_secret);
        }
        return data;
    }

    // Called by the login page right after a successful ONLINE login, while
    // the password is still in memory. Enrols (or renews) this device under
    // that password and leaves the person unlocked. Safe to call every login:
    // a returning person keeps their device id and all their local data.
    async function provisionAfterLogin(username, password) {
        const existing = (await OfflineDB.listAccounts()).find(
            (a) => a.username && a.username.toLowerCase() === String(username).trim().toLowerCase());
        const data = await enroll(password, null, { deviceId: existing ? existing.device_id : null, bootstrap: false });
        sessionStorage.setItem(SESSION_KEY, JSON.stringify({
            device_id: data.device_id, device_secret: data.device_secret, user: data.user,
            started_at: new Date().toISOString(),
        }));
        clearThrottle(data.device_id);
        requestPersistence().catch(() => {});
        // The earlier version of the app kept its own saved offline logins here. They are
        // replaced by the one just created, so remove the leftover.
        try { indexedDB.deleteDatabase("offlineAuthDB"); } catch (e) { /* not present */ }
        return data;
    }

    // Ask the browser not to clear this site's data when the phone runs low on
    // storage — unsynced work lives here. Best effort; the Sync screen warns
    // when it hasn't been granted.
    async function requestPersistence() {
        try {
            if (navigator.storage && navigator.storage.persist) {
                if (await navigator.storage.persisted()) return true;
                return await navigator.storage.persist();
            }
        } catch (e) { /* not supported */ }
        return false;
    }

    async function storageInfo() {
        const info = { persisted: false, usage: null, quota: null };
        try {
            if (navigator.storage && navigator.storage.persisted) info.persisted = await navigator.storage.persisted();
            if (navigator.storage && navigator.storage.estimate) {
                const e = await navigator.storage.estimate();
                info.usage = e.usage; info.quota = e.quota;
            }
        } catch (e) { /* ignore */ }
        return info;
    }

    // Slow down guessing at the lock screen: after 5 wrong tries the device
    // makes the person wait (30s, doubling, up to 15 min).
    const THROTTLE_FREE_TRIES = 5;
    function throttleKey(deviceId) { return "srs_unlock_" + deviceId; }
    function readThrottle(deviceId) {
        try { return JSON.parse(localStorage.getItem(throttleKey(deviceId)) || "null") || { fails: 0, until: 0 }; }
        catch (e) { return { fails: 0, until: 0 }; }
    }
    function clearThrottle(deviceId) { try { localStorage.removeItem(throttleKey(deviceId)); } catch (e) { /* ignore */ } }
    function noteFailure(deviceId) {
        const t = readThrottle(deviceId);
        t.fails += 1;
        if (t.fails >= THROTTLE_FREE_TRIES) {
            t.until = Date.now() + Math.min(15 * 60000, 30000 * Math.pow(2, t.fails - THROTTLE_FREE_TRIES));
        }
        try { localStorage.setItem(throttleKey(deviceId), JSON.stringify(t)); } catch (e) { /* ignore */ }
    }

    function authError(code, message) {
        const e = new Error(message);
        e.code = code;
        return e;
    }

    async function listAccounts() {
        return OfflineDB.listAccounts();
    }

    // Step 2 — works fully offline. `secret` is the person's password.
    async function unlock(deviceId, secret) {
        const accounts = await OfflineDB.listAccounts();
        const account = accounts.find((a) => a.device_id === deviceId);
        if (!account) throw authError("not_enrolled", "This device isn't enrolled for offline access yet.");
        const throttle = readThrottle(deviceId);
        if (throttle.until && throttle.until > Date.now()) {
            const secs = Math.ceil((throttle.until - Date.now()) / 1000);
            throw authError("throttled", `Too many wrong attempts. Try again in ${secs} second${secs === 1 ? "" : "s"}.`);
        }
        let payload;
        try {
            payload = await OfflineCrypto.decrypt(secret, account.encrypted);
        } catch (e) {
            noteFailure(deviceId);
            throw authError("wrong_password", "Incorrect password.");
        }
        clearThrottle(deviceId);
        if (account.expires_at && account.expires_at < new Date().toISOString()) {
            // The person's data and unsynced work are untouched — only signing in
            // (which needs the internet) renews access.
            throw authError("expired", "It has been a while since this device connected. Log in online once to renew offline access — everything you entered is still saved here and will sync then.");
        }
        const sessionData = {
            device_id: payload.device_id,
            device_secret: payload.device_secret,
            user: payload.user,
            started_at: new Date().toISOString(),
        };
        sessionStorage.setItem(SESSION_KEY, JSON.stringify(sessionData));
        requestPersistence().catch(() => {});
        verifyOnline().catch(() => { /* fine — we're offline, that's the point */ });
        return sessionData.user;
    }

    // Returns the current unlocked session, or null if there isn't one or
    // it has expired (clearing it in that case).
    function getSession() {
        const raw = sessionStorage.getItem(SESSION_KEY);
        if (!raw) return null;
        let data;
        try { data = JSON.parse(raw); } catch (e) { sessionStorage.removeItem(SESSION_KEY); return null; }
        const ageHours = (Date.now() - new Date(data.started_at).getTime()) / 3.6e6;
        if (ageHours > MAX_SESSION_HOURS) {
            sessionStorage.removeItem(SESSION_KEY);
            return null;
        }
        return data;
    }

    function lock() {
        sessionStorage.removeItem(SESSION_KEY);
    }

    async function forgetDevice(deviceId) {
        await OfflineDB.deleteAccount(deviceId);
        const current = getSession();
        if (current && current.device_id === deviceId) lock();
    }

    // Step 4 — call whenever navigator.onLine flips true. Confirms the
    // credential is still valid and slides its expiry forward; forces the
    // session closed if the account/school is no longer in good standing.
    async function verifyOnline() {
        const session = getSession();
        const reachable = (typeof Connectivity !== "undefined") ? Connectivity.isOnline() : navigator.onLine;
        if (!session || !reachable) return null;
        const res = await fetch("/api/offline/verify", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ device_id: session.device_id, device_secret: session.device_secret }),
        });
        if (!res.ok) return null;
        const data = await res.json();
        if (data.status !== "ok") {
            const reasons = {
                revoked: "This device's offline access has been revoked.",
                expired: "This device's offline access has expired.",
                school_suspended: "This school's account is suspended.",
                school_archived: "This school's account has been archived.",
                not_found: "This device is no longer recognized. Please re-enroll.",
                bad_secret: "This device's credential is no longer valid. Please re-enroll.",
            };
            lock();
            throw new Error(reasons[data.status] || "Offline access is no longer valid on this device.");
        }
        const accounts = await OfflineDB.listAccounts();
        const account = accounts.find((a) => a.device_id === session.device_id);
        if (account) {
            account.expires_at = data.expires_at;
            await OfflineDB.saveAccount(account);
        }
        return data;
    }

    function hasRole(...roles) {
        const session = getSession();
        return !!session && roles.includes(session.user.role);
    }

    return { enroll, provisionAfterLogin, listAccounts, unlock, getSession, lock, forgetDevice, verifyOnline, hasRole, requestPersistence, storageInfo };
})();
