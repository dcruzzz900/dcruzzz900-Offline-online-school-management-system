// Shared by the engine end-to-end tests: an in-memory stand-in for IndexedDB
// (same API surface as static/js/offline-db.js) and a loader that runs the REAL
// static/js/sync-engine.js against a live Flask server, as one simulated device.
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const nodeCrypto = require("crypto");

// ---- fake IndexedDB layer (same API surface as offline-db.js) -------------
function makeDb() {
    const stores = {}, meta = {};
    const st = (e) => (stores[e] = stores[e] || new Map());
    const clone = (x) => (x === undefined ? x : JSON.parse(JSON.stringify(x)));
    return {
        async putRecord(_s, e, r) { st(e).set(r.client_uuid, clone(r)); },
        async putRecords(_s, e, rs) { rs.forEach((r) => st(e).set(r.client_uuid, clone(r))); },
        async deleteRecord(_s, e, u) { st(e).delete(u); },
        async getRecord(_s, e, u) { return clone(st(e).get(u)); },
        async getAll(_s, e, o) { return [...st(e).values()].filter((r) => (o && o.includeDeleted) || !r.is_deleted).map(clone); },
        ENTITY_STORES: ["students","scores","attendance_records","staff_attendance","student_term_info","classes","subjects","users","sessions","terms","class_subjects","grading_config","grade_scale","enrollments","skill_traits","student_skill_ratings","actions"],
        async getByStatus(_s, e, status) { return [...st(e).values()].filter((r) => r._sync && r._sync.status === status).map(clone); },
        async getPendingCounts() { return { pending: 0, conflict: 0, failed: 0 }; },
        async setMeta(_s, k, v) { meta[k] = v; },
        async getMeta(_s, k) { return meta[k] === undefined ? null : meta[k]; },
        _stores: stores, _meta: meta,
    };
}

function makeDevice(cred, label, baseUrl, SCHOOL, sharedDb) {
    const net = { online: true, dropResponses: 0 };
    const db = sharedDb || makeDb();
    const session = { device_id: cred.device_id, device_secret: cred.device_secret, user: cred.user };
    const sandbox = {
        OfflineDB: db,
        OfflineAuth: { getSession: () => session },
        navigator: { get onLine() { return net.online; } },
        document: { dispatchEvent() {} }, CustomEvent: class { constructor(n, o) { this.detail = o && o.detail; } },
        window: { addEventListener() {} }, crypto: nodeCrypto.webcrypto, console, setInterval, clearInterval,
        Blob, FileReader: class {},
        fetch: async (url, opts) => {
            if (!net.online) throw new TypeError("offline");
            const res = await fetch(baseUrl + url, opts);
            if (net.dropResponses > 0 && opts && opts.method === "POST" && url.includes("/api/sync/push")) {
                net.dropResponses--;
                await res.text();                    // server processed it, but the device never hears back
                throw new TypeError("connection dropped");
            }
            return res;
        },
    };
    vm.createContext(sandbox);
    const src = fs.readFileSync(path.join(__dirname, "..", "..", "static", "js", "sync-engine.js"), "utf8");
    vm.runInContext(src + "\n;this.SyncEngine = SyncEngine;", sandbox);
    return { name: label, db, net, cred, session, E: sandbox.SyncEngine,
        sync: () => sandbox.SyncEngine.syncNow(SCHOOL, session.device_id, session.device_secret),
        boot: () => sandbox.SyncEngine.bootstrap(SCHOOL, session.device_id, session.device_secret),
        all: (e) => db.getAll(SCHOOL, e),
    };
}


module.exports = { makeDb, makeDevice };
