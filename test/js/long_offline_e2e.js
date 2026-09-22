// A device that has been offline for weeks. Runs the REAL sync engine (Node)
// against a live server. The server side of "weeks passing" (other people
// editing, records deleted, the credential expiring) is done through the
// test-only /api/__test__/* routes the Python test registers.
//   node long_offline_e2e.js <baseUrl> <ctx.json>
const fs = require("fs");
const { makeDevice: mk } = require("./harness");
const [baseUrl, ctxFile] = process.argv.slice(2);
const ctx = JSON.parse(fs.readFileSync(ctxFile, "utf8"));
const SCHOOL = ctx.school_id;
const makeDevice = (cred, label, sharedDb) => mk(cred, label, baseUrl, SCHOOL, sharedDb);
let failures = 0;
const check = (label, cond, extra) => {
    if (!cond) { failures++; console.log("FAIL:", label, extra === undefined ? "" : JSON.stringify(extra)); }
    else console.log("ok:  ", label);
};
const admin = (cred) => ({ "X-Device-Id": cred.device_id, "X-Device-Secret": cred.device_secret, "Content-Type": "application/json" });
async function server(path, body) {
    const r = await fetch(baseUrl + "/api/__test__/" + path, { method: "POST", headers: admin(ctx.credA), body: JSON.stringify(body || {}) });
    return r.json();
}
const counts = async (dev) => dev.db.getPendingCounts(SCHOOL);
async function statusCounts(dev) {
    const out = { pending: 0, failed: 0, conflict: 0, synced: 0 };
    for (const e of dev.db.ENTITY_STORES) for (const r of await dev.db.getAll(SCHOOL, e)) if (r._sync) out[r._sync.status] = (out[r._sync.status] || 0) + 1;
    return out;
}

(async () => {
    const T = makeDevice(ctx.credT, "teacher-phone");
    await T.boot();
    const A = makeDevice(ctx.credA, "admin-tablet");
    await A.boot();
    const students = (await T.all("students")).sort((a, b) => a.admission_no.localeCompare(b.admission_no));
    const subjects = (await T.all("subjects")).sort((a, b) => a.id - b.id).slice(0, 4);
    check("teacher device has the class", students.length >= 30 && subjects.length === 4, { students: students.length });

    // ================= WEEKS OFFLINE: the teacher keeps working =================
    T.net.online = false;
    const t0 = Date.now();
    const dates = Array.from({ length: 20 }, (_, i) => `2026-08-${String(3 + i).padStart(2, "0")}`);
    let queued = 0;
    for (const st of students) {
        for (const d of dates) {
            await T.E.queueChange(SCHOOL, "attendance_records", "create",
                { student_id: st.id, class_id: ctx.cls, term_id: ctx.term, date: d, status: (st.id + d.length) % 7 === 0 ? "absent" : "present", recorded_by: ctx.credT.user.user_id });
            queued++;
        }
        for (const [i, sb] of subjects.entries()) {
            const existing = (await T.all("scores")).find((r) => r.student_id === st.id && r.subject_id === sb.id);
            if (existing) await T.E.queueChange(SCHOOL, "scores", "update", { ca1: 18 }, existing.client_uuid);
            else await T.E.queueChange(SCHOOL, "scores", "create", { student_id: st.id, subject_id: sb.id, term_id: ctx.term, ca1: 15 + i, ca2: 14, ca3: 0, exam: 40 + i });
            queued++;
        }
    }
    const queueSecs = (Date.now() - t0) / 1000;
    const before = await statusCounts(T);
    check(`queued ${queued} changes offline (${queueSecs.toFixed(1)}s)`, before.pending === queued, before);

    // ================= meanwhile, on the server =================
    const prep = await server("weeks_pass", {});
    check("server side of the story ran", prep.ok, prep);

    // ================= reconnect with an EXPIRED credential =================
    T.net.online = true;
    const r1 = await T.sync();
    check("expired credential is reported, not treated as a failure", r1.authError === "expired", r1);
    const afterExpired = await statusCounts(T);
    check("every queued change is still waiting, untouched", afterExpired.pending === queued && !afterExpired.failed && !afterExpired.conflict, afterExpired);
    check("the reason is remembered for the screen", (await T.db.getMeta(SCHOOL, "auth_problem")).status === "expired");

    // ================= the person logs in online -> same device, new secret =================
    const renewed = await server("renew", { device_id: ctx.credT.device_id });
    check("renewal keeps the device id", renewed.device_id === ctx.credT.device_id && renewed.device_secret !== ctx.credT.device_secret);
    T.session.device_secret = renewed.device_secret;
    // a full re-download (what the old "enable offline access" button did) must not eat unsynced work
    const T2 = makeDevice({ ...ctx.credT, device_secret: renewed.device_secret }, "same-phone-redownload", T.db);
    await T2.boot();
    const afterBoot = await statusCounts(T);
    const stillOurs = afterBoot.pending + afterBoot.conflict + afterBoot.failed;
    check("a full re-download keeps all unsynced work", stillOurs === queued, afterBoot);

    // reset any conflict flags a re-download would have set so we test the push path from a clean state? (no: keep as-is - this is what a user would have)
    const t1 = Date.now();
    const r2 = await T.sync();
    const syncSecs = (Date.now() - t1) / 1000;
    check(`sync after renewal completed (${syncSecs.toFixed(1)}s for ${queued} changes)`, !r2.authError && r2.push, r2);
    const after = await statusCounts(T);
    console.log("   local after sync:", JSON.stringify(after), " push:", JSON.stringify(r2.push));
    check("no silent loss: everything is synced, or visibly failed/in conflict", after.pending === 0, after);

    // ================= what reached the server =================
    const v = await server("verify_weeks", {});
    for (const [k, ok] of Object.entries(v.checks)) check("server: " + k, ok, v.detail && v.detail[k]);

    // ================= a second device that was offline that long pulls a LOT of changes =================
    const mid = await server("bulk_changes", {});
    await A.sync();
    const serverAtt = mid.attendance_rows;
    const localAtt = (await A.all("attendance_records")).length;
    check(`admin tablet pulled a big delta in pages (${localAtt}/${serverAtt} attendance rows)`, localAtt === serverAtt, { localAtt, serverAtt });

    console.log(failures ? `\n${failures} FAILED` : "\nlong-offline e2e OK");
    process.exit(failures ? 1 : 0);
})().catch((e) => { console.error("harness error:", e); process.exit(3); });
