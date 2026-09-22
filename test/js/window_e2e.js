// The device keeps only the ACTIVE session's scores and the active term's attendance. When
// the school moves to a new term the device notices, downloads the new window and drops the
// old one - without touching anything it hasn't synced yet.
const fs = require("fs");
const { makeDevice: mk } = require("./harness");
const [baseUrl, ctxFile] = process.argv.slice(2);
const ctx = JSON.parse(fs.readFileSync(ctxFile, "utf8"));
const SCHOOL = ctx.school_id;
const A = mk(ctx.credA, "admin", baseUrl, SCHOOL);
let failures = 0;
const check = (label, cond, extra) => { if (!cond) { failures++; console.log("FAIL:", label, extra === undefined ? "" : JSON.stringify(extra)); } else console.log("ok:  ", label); };
const count = async (e, f) => (await A.all(e)).filter(f || (() => true)).length;

(async () => {
    await A.boot();
    check("only the active session's scores came down", await count("scores", (r) => r.term_id === ctx.t1 || r.term_id === ctx.t2) === ctx.scores_current
        && await count("scores", (r) => r.term_id === ctx.t_old) === 0);
    check("attendance: only the active term's", await count("attendance_records", (r) => r.term_id === ctx.t1) === ctx.att_t1
        && await count("attendance_records", (r) => r.term_id === ctx.t2) === 0);
    check("the window is remembered", (await A.db.getMeta(SCHOOL, "data_window")) === `${ctx.session}:${ctx.t1}`, await A.db.getMeta(SCHOOL, "data_window"));

    // unsynced work made offline against the OLD term
    A.net.online = false;
    const stu = (await A.all("students"))[0];
    await A.E.queueChange(SCHOOL, "attendance_records", "create", { student_id: stu.id, class_id: ctx.cls, term_id: ctx.t1, date: "2026-09-30", status: "absent", recorded_by: ctx.credA.user.user_id });
    A.net.online = true;

    // the admin moves the school to the 2nd term
    await fetch(baseUrl + "/api/__test__/switch_term", { method: "POST", headers: { "X-Device-Id": ctx.credA.device_id, "X-Device-Secret": ctx.credA.device_secret } });
    const r = await A.sync();
    check("the device noticed the new term and re-downloaded", !!(r.pull && r.pull.rebootstrap), r.pull);
    check("new window remembered", (await A.db.getMeta(SCHOOL, "data_window")) === `${ctx.session}:${ctx.t2}`);
    check("new term's attendance is on the device", await count("attendance_records", (r2) => r2.term_id === ctx.t2) === ctx.att_t2);
    check("old term's synced attendance was dropped", await count("attendance_records", (r2) => r2.term_id === ctx.t1 && r2._sync.status === "synced") === 0);
    check("nothing is left waiting (the offline entry was pushed before the old window was dropped)", (await A.db.getPendingCounts(SCHOOL)).pending === 0);
    console.log(failures ? `\n${failures} FAILED` : "\nwindow e2e OK");
    process.exit(failures ? 1 : 0);
})().catch((e) => { console.error("harness error:", e); process.exit(3); });
