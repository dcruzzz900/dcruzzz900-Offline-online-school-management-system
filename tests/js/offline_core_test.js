// Run: node tests/js/offline_core_test.js   (engine tested with an in-memory store, real AES-GCM and a scripted fake server)
const assert = require("assert");
const { createCore, memoryStore, makeCrypto } = require("../../static/js/offline/offline-core.js");
let pass = 0; const t = async (name, fn) => { try { await fn(); pass++; } catch (e) { console.log("FAIL:", name, "\n ", e.message); process.exitCode = 1; } };

function fakeServer() {
  const s = { online: true, authed: true, log: [], seen: {}, mode: {}, clock: 1e12 };
  const res = (status, body, hdr = {}, extra = {}) => ({ ok: status >= 200 && status < 300, status, redirected: false, url: "", ...extra,
    headers: { get: (k) => hdr[k] || hdr[k.toLowerCase()] || null }, clone() { return this; }, json: async () => body });
  s.fetch = async (url, init = {}) => {
    if (!s.online) throw new TypeError("network down");
    if (url === "/api/sync/ping") return res(200, { ok: true });
    if (url === "/api/sync/session") return res(200, { authenticated: s.authed, fingerprint: "fp-teacher", csrf: "tok-1", offline_window_days: 7 });
    if (url === "/api/sync/report") return res(200, { ok: true });
    const id = init.headers["X-Change-Id"]; s.log.push({ url, id, headers: init.headers, body: init.body });
    if (s.mode[id]) return s.mode[id](id);
    if (s.seen[id]) return res(200, s.seen[id], { "X-Sync-Ack": id, "X-Sync-Duplicate": "1" });
    const out = { ok: true, updated_at: "v-" + s.log.length }; s.seen[id] = out;
    return res(200, out, { "X-Sync-Ack": id });
  };
  return s;
}
async function make(server, opts = {}) {
  const store = memoryStore(); let now = server.clock;
  const core = createCore({ store, crypto: opts.plain ? makeCrypto(null, store) : makeCrypto(globalThis.crypto.subtle, store), fetch: server.fetch, now: () => now, uuid: (() => { let n = 0; return () => "uuid-" + (++n).toString().padStart(8, "0"); })(),
    FormData: class { constructor() { this.p = []; } append(k, v) { this.p.push([k, v]); } }, Blob: class { constructor(p, o) { this.parts = p; this.type = o.type; } } });
  await core.init(); await store._x; await store.metaSet("fingerprint", "fp-teacher"); await core.init();
  core.tick = (ms) => { now += ms; };
  return { core, store };
}
const score = (n, ca1) => ({ method: "POST", url: "/api/scores/1/1/row", kind: "json", body: { student_id: n, ca1: String(ca1) }, entityKey: "score:" + n, baseVersion: "v0" });

(async () => {
  await t("queued changes survive and replay in order when the server returns", async () => {
    const sv = fakeServer(), { core } = await make(sv); sv.online = false;
    assert.strictEqual(await core.checkConnection(), false); assert.strictEqual(core.state().status, "offline");
    await core.enqueue(score(1, 10)); await core.enqueue(score(2, 12)); await core.enqueue(score(3, 14));
    assert.strictEqual(core.state().pending, 3);
    sv.online = true; await core.syncNow();
    assert.deepStrictEqual(sv.log.map((l) => JSON.parse(l.body).student_id), [1, 2, 3], "oldest first");
    assert.strictEqual(core.state().pending, 0); assert.strictEqual(core.state().status, "completed"); assert.ok(core.state().lastSync);
  });
  await t("each replay carries change id, csrf, replay flag, device, capture time, base version", async () => {
    const sv = fakeServer(), { core } = await make(sv); await core.enqueue(score(1, 10)); await core.syncNow();
    const h = sv.log[0].headers; assert.strictEqual(h["X-CSRF-Token"], "tok-1"); assert.strictEqual(h["X-Offline-Replay"], "1");
    assert.strictEqual(h["X-Base-Version"], "v0"); assert.ok(h["X-Change-Id"] && h["X-Captured-At"] && h["X-Device-Id"].startsWith("dev-"));
  });
  await t("queued payloads are really encrypted at rest (AES-GCM) and round-trip", async () => {
    const sv = fakeServer(), { core, store } = await make(sv);
    await core.enqueue({ ...score(1, 10), body: { student_id: 1, secret: "Chinedu Okafor 97" } });
    const raw = (await store.all())[0]; assert.strictEqual(raw.enc, true);
    assert.ok(!JSON.stringify(raw).includes("Chinedu"), "plaintext must not be stored");
    await core.syncNow(); assert.ok(sv.log[0].body.includes("Chinedu Okafor 97"));
  });
  await t("without WebCrypto the engine still works and says it is not encrypted", async () => {
    const sv = fakeServer(), { core, store } = await make(sv, { plain: true }); await core.enqueue(score(1, 1));
    assert.strictEqual((await store.all())[0].enc, false); assert.strictEqual(core.state().encrypted, false);
  });
  await t("editing a still-queued record replaces the earlier edit and keeps the ORIGINAL base version", async () => {
    const sv = fakeServer(), { core } = await make(sv);
    await core.enqueue({ ...score(1, 10), baseVersion: "v-original" }); await core.enqueue({ ...score(1, 15), baseVersion: "v-should-be-ignored" });
    assert.strictEqual(core.state().pending, 1); await core.syncNow();
    assert.strictEqual(sv.log.length, 1); assert.strictEqual(JSON.parse(sv.log[0].body).ca1, "15"); assert.strictEqual(sv.log[0].headers["X-Base-Version"], "v-original");
  });
  await t("a duplicate (answered from the server's record) counts as done: no double apply, queue empties", async () => {
    const sv = fakeServer(), { core } = await make(sv); await core.enqueue({ ...score(1, 10), id: "fixed-id-0001" }); sv.seen["fixed-id-0001"] = { ok: true };
    await core.syncNow(); assert.strictEqual(core.state().pending, 0); assert.strictEqual(core.state().status, "completed");
  });
  await t("network drop mid-sync stops, keeps order, backs off, then recovers automatically", async () => {
    const sv = fakeServer(), { core } = await make(sv); await core.enqueue(score(1, 1)); await core.enqueue(score(2, 2));
    let calls = 0; const orig = sv.fetch;
    sv.fetch = async (u, i) => { if (/scores/.test(u) && ++calls === 1) throw new TypeError("dropped"); return orig(u, i); };
    const c2 = createCore({ store: core._store, crypto: makeCrypto(globalThis.crypto.subtle, core._store), fetch: (u, i) => sv.fetch(u, i), now: () => sv.clock, uuid: () => "x" + Math.random().toString(16).slice(2, 12) });
    await c2.init(); await c2.syncNow();
    assert.strictEqual(c2.state().pending, 2, "nothing lost"); assert.strictEqual(c2.state().status, "failed");
    sv.clock += 3000; await c2.syncNow(); assert.strictEqual(c2.state().pending, 0, "recovered once the back-off passed"); assert.strictEqual(c2.state().status, "completed");
  });
  await t("5xx is retried with back-off, and gives up to 'Failed' after the attempt limit (never dropped)", async () => {
    const sv = fakeServer(), { core, store } = await make(sv); const e = await core.enqueue(score(1, 1));
    sv.mode[e.id] = () => ({ ok: false, status: 503, redirected: false, headers: { get: (k) => (k === "X-Sync-Ack" ? e.id : null) }, clone() { return this; }, json: async () => ({}) });
    for (let i = 0; i < 9; i++) { sv.clock += 700000; await core.syncNow({ manual: true }); }
    const q = await core.listQueue(); assert.strictEqual(q.length, 1); assert.strictEqual(q[0].state, "failed"); assert.ok(/Retry/.test(q[0].error));
  });
  await t("a rule failure (423 locked) shows the server's message as Failed and is kept for retry/discard", async () => {
    const sv = fakeServer(), { core } = await make(sv); const e = await core.enqueue(score(1, 1));
    sv.mode[e.id] = () => ({ ok: false, status: 423, redirected: false, headers: { get: (k) => (k === "X-Sync-Ack" ? e.id : null) }, clone() { return this; }, json: async () => ({ error: "Scores are locked" }) });
    await core.syncNow(); const q = await core.listQueue();
    assert.strictEqual(q[0].state, "failed"); assert.strictEqual(q[0].error, "Scores are locked"); assert.strictEqual(core.state().failed, 1); assert.strictEqual(core.state().status, "failed");
    delete sv.mode[e.id]; await core.retry(e.id); assert.strictEqual((await core.listQueue()).length, 0, "retry succeeds once the server accepts it");
  });
  await t("a conflict is parked for the administrator and not retried", async () => {
    const sv = fakeServer(), { core } = await make(sv); const e = await core.enqueue(score(1, 1));
    sv.mode[e.id] = () => ({ ok: false, status: 409, redirected: false, headers: { get: (k) => (k === "X-Sync-Ack" ? e.id : null) }, clone() { return this; }, json: async () => ({ conflict: true, error: "Admin must review" }) });
    await core.syncNow(); assert.strictEqual(core.state().conflicts, 1); const n = sv.log.length; sv.clock += 1e6; await core.syncNow(); assert.strictEqual(sv.log.length, n, "not re-sent");
  });
  await t("a 200 WITHOUT the server's acknowledgement (e.g. a login page) is NOT treated as success", async () => {
    const sv = fakeServer(), { core } = await make(sv); const e = await core.enqueue(score(1, 1));
    sv.mode[e.id] = () => ({ ok: true, status: 200, redirected: true, url: "https://x/login", headers: { get: () => null }, clone() { return this; }, json: async () => { throw new Error("html"); } });
    await core.syncNow(); assert.strictEqual(core.state().pending, 1, "still queued");
    sv.mode[e.id] = () => ({ ok: true, status: 200, redirected: false, headers: { get: () => null }, clone() { return this; }, json: async () => ({}) });
    sv.clock += 1e6; await core.syncNow(); assert.strictEqual(core.state().pending, 1, "no ack, still queued");
  });
  await t("signed-out device keeps the queue and reports 'Sync Failed' with a clear message", async () => {
    const sv = fakeServer(), { core } = await make(sv); await core.enqueue(score(1, 1)); sv.authed = false; await core.syncNow();
    assert.strictEqual(core.state().pending, 1); assert.strictEqual(core.state().status, "failed"); assert.ok(/sign in/i.test(core.state().error));
  });
  await t("changes belong to their user: another user on the same device never replays them", async () => {
    const sv = fakeServer(), { core, store } = await make(sv); await core.enqueue(score(1, 1));
    await store.metaSet("fingerprint", "fp-other"); const orig = sv.fetch;
    sv.fetch = async (u, i) => { const r = await orig(u, i); if (u === "/api/sync/session") r.json = async () => ({ authenticated: true, fingerprint: "fp-other", csrf: "t", offline_window_days: 7 }); return r; };
    const c2 = createCore({ store, crypto: makeCrypto(globalThis.crypto.subtle, store), fetch: (u, i) => sv.fetch(u, i), now: () => sv.clock, uuid: () => "y1234567" });
    await c2.init(); await c2.syncNow();
    assert.strictEqual(sv.log.length, 0, "nothing sent"); assert.strictEqual((await c2.listQueue())[0].mine, false); assert.strictEqual(c2.state().otherUsers, 1);
  });
  await t("offline access expires after the verification window", async () => {
    const sv = fakeServer(), { core } = await make(sv); assert.strictEqual(await core.offlineAllowed(), false);
    await core.sessionInfo(); assert.strictEqual(await core.offlineAllowed(), true);
    core.tick(6 * 86400000); assert.strictEqual(await core.offlineAllowed(), true, "inside the 7-day window");
    core.tick(2 * 86400000); assert.strictEqual(await core.offlineAllowed(), false, "8 days after the last online sign-in check: locked until reconnected");
    await core.sessionInfo(); assert.strictEqual(await core.offlineAllowed(), true, "reconnecting renews it");
  });
  await t("form uploads: files are stored encrypted, size-limited, and rebuilt for replay with a fresh CSRF token", async () => {
    const sv = fakeServer(), { core, store } = await make(sv);
    const buf = new TextEncoder().encode("PASSPORT-BYTES").buffer;
    await core.enqueue({ method: "POST", url: "/students/5/edit", kind: "form", body: [["csrf_token", "STALE"], ["name", "Ada"]], files: [{ field: "passport", name: "p.jpg", type: "image/jpeg", buffer: buf }] });
    assert.ok(!JSON.stringify((await store.all())[0]).includes("PASSPORT"), "file bytes not in plaintext");
    await core.syncNow(); const body = sv.log[0].body.p;
    assert.deepStrictEqual(body.filter((p) => p[0] === "csrf_token").map((p) => p[1]), ["tok-1"]); assert.ok(body.some((p) => p[0] === "passport"));
    let err; try { await core.enqueue({ method: "POST", url: "/x", kind: "form", body: [], files: [{ field: "f", name: "n", type: "t", buffer: new ArrayBuffer(6 * 1024 * 1024) }] }); } catch (e) { err = e; }
    assert.ok(err && /5 MB/.test(err.message));
  });
  await t("status events fire: syncing -> completed, with progress", async () => {
    const sv = fakeServer(), { core } = await make(sv); const seen = []; core.on("status", (s) => seen.push(s.status + ":" + s.progress.done + "/" + s.progress.total));
    await core.enqueue(score(1, 1)); await core.enqueue(score(2, 2)); await core.syncNow();
    assert.ok(seen.includes("syncing:0/2") && seen.includes("syncing:2/2") && seen[seen.length - 1].startsWith("completed"), seen.join(" "));
  });
  await t("not signed in: nothing can be queued", async () => {
    const sv = fakeServer(), store = memoryStore(), core = createCore({ store, crypto: makeCrypto(null, store), fetch: sv.fetch });
    await core.init(); let err; try { await core.enqueue(score(1, 1)); } catch (e) { err = e; } assert.ok(err);
  });
  console.log(`JS PASSED ${pass}`);
})();
