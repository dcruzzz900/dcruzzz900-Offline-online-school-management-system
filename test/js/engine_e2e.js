// Runs the REAL static/js/sync-engine.js in Node (with an in-memory stand-in
// for IndexedDB) against a live copy of the Flask server, simulating two
// devices working offline and reconnecting.
//   node engine_e2e.js <baseUrl> <ctx.json>
const fs = require("fs");
const { makeDevice: mk } = require("./harness");

const [baseUrl, ctxFile] = process.argv.slice(2);
const ctx = JSON.parse(fs.readFileSync(ctxFile, "utf8"));
const SCHOOL = ctx.school_id;
const makeDevice = (cred, label) => mk(cred, label, baseUrl, SCHOOL);

let failures = 0;
function check(label, cond, extra) {
    if (!cond) { failures++; console.log("FAIL:", label, extra === undefined ? "" : JSON.stringify(extra)); }
    else console.log("ok:  ", label);
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
    const A = makeDevice(ctx.credA, "A"), B = makeDevice(ctx.credB, "B");
    await A.boot(); await B.boot();

    const cellOf = async (dev) => (await dev.all("scores")).find((r) => r.student_id === ctx.student && r.subject_id === ctx.subject);
    check("both devices bootstrapped the seeded score", !!(await cellOf(A)) && !!(await cellOf(B)));
    check("school profile stored", (await A.db.getMeta(SCHOOL, "school_profile")).name === "My School");
    check("no credentials in local DB", (await A.all("users")).every((u) => !("password_hash" in u)));
    check("grading settings available offline", (await A.all("grading_config")).length === 1 && (await A.all("grade_scale")).length >= 5);

    // 1. Disjoint edits on the same score row while BOTH are offline -> merged
    A.net.online = false; B.net.online = false;
    const a0 = await cellOf(A), b0 = await cellOf(B);
    await A.E.queueChange(SCHOOL, "scores", "update", { ca1: a0.ca1 + 2 }, a0.client_uuid);
    await B.E.queueChange(SCHOOL, "scores", "update", { exam: b0.exam + 5 }, b0.client_uuid);
    A.net.online = true; B.net.online = true;
    const ra = await A.sync(); const rb = await B.sync(); await A.sync();
    check("A synced its edit", ra.push.synced === 1 && ra.push.conflicts === 0, ra.push);
    check("B's edit merged, not conflicted", rb.push.synced === 1 && rb.push.conflicts === 0, rb.push);
    const ca = await cellOf(A), cb = await cellOf(B);
    check("both devices now hold BOTH edits", ca.ca1 === a0.ca1 + 2 && ca.exam === b0.exam + 5 && cb.ca1 === a0.ca1 + 2 && cb.exam === b0.exam + 5, { ca, cb });

    // 2. Same field edited differently -> conflict on the 2nd device, nothing lost; keep mine resolves
    A.net.online = false; B.net.online = false;
    const a1 = await cellOf(A), b1 = await cellOf(B);
    await A.E.queueChange(SCHOOL, "scores", "update", { ca2: 3 }, a1.client_uuid);
    await B.E.queueChange(SCHOOL, "scores", "update", { ca2: 9 }, b1.client_uuid);
    A.net.online = true; B.net.online = true;
    await A.sync(); const rb2 = await B.sync();
    check("same-field clash is a conflict", rb2.push.conflicts === 1, rb2.push);
    const bc = await cellOf(B);
    check("conflicting record keeps local value + carries server's", bc._sync.status === "conflict" && bc.ca2 === 9 && bc._sync.server_data.ca2 === 3 && bc._sync.conflicting_fields.includes("ca2"), bc._sync);
    await B.E.resolveConflict(SCHOOL, "scores", bc.client_uuid, true);
    const rb3 = await B.sync(); await A.sync();
    check("keep-mine then syncs cleanly", rb3.push.synced === 1 && rb3.push.conflicts === 0, rb3.push);
    check("A sees B's resolved value", (await cellOf(A)).ca2 === 9);

    // 3. Lost response: server applied the change, device never heard -> retry must not double-apply or conflict
    A.net.dropResponses = 1;
    await A.E.queueChange(SCHOOL, "scores", "update", { ca1: 1 }, (await cellOf(A)).client_uuid);
    let dropped = false;
    try { await A.sync(); } catch (e) { dropped = true; }
    const still = await cellOf(A);
    check("a dropped reply never turns into a conflict with ourselves", still._sync.status !== "conflict", still._sync);
    const rr = await A.sync();
    check("nothing left waiting after the retry", (await A.db.getByStatus(SCHOOL, "scores", "pending")).length === 0
        && (await A.db.getByStatus(SCHOOL, "scores", "conflict")).length === 0, rr);
    check("the change landed exactly once", (await cellOf(A)).ca1 === 1 && (await cellOf(B).catch(() => null)) !== null);

    // 4. Two devices create the SAME score cell offline (new student, so neither has a row) -> one row
    const newStudent = { admission_no: "900", first_name: "Sync", last_name: "Test", gender: "F", class_id: ctx.cls, is_active: 1 };
    await A.E.queueChange(SCHOOL, "students", "create", newStudent);
    await A.sync(); await B.sync();
    const sA = (await A.all("students")).find((s) => s.admission_no === "900");
    check("new student synced to A with server id", !!(sA && sA.id));
    check("new student reached B", !!(await B.all("students")).find((s) => s.admission_no === "900"));
    A.net.online = false; B.net.online = false;
    await A.E.queueChange(SCHOOL, "scores", "create", { student_id: sA.id, subject_id: ctx.subject, term_id: ctx.term, ca1: 8, ca2: 0, ca3: 0, exam: 0 });
    await B.E.queueChange(SCHOOL, "scores", "create", { student_id: sA.id, subject_id: ctx.subject, term_id: ctx.term, ca1: 0, ca2: 0, ca3: 0, exam: 44 });
    A.net.online = true; B.net.online = true;
    await A.sync(); const rbn = await B.sync(); await A.sync();
    check("second creator merged, no error", rbn.push.synced === 1 && rbn.push.conflicts === 0 && rbn.push.errors === 0, rbn.push);
    const cellsA = (await A.all("scores")).filter((r) => r.student_id === sA.id);
    const cellsB = (await B.all("scores")).filter((r) => r.student_id === sA.id);
    check("exactly one local row per device, holding both marks", cellsA.length === 1 && cellsB.length === 1 && cellsA[0].ca1 === 8 && cellsA[0].exam === 44 && cellsB[0].ca1 === 8 && cellsB[0].exam === 44, { cellsA, cellsB });

    // 5. Online hard delete reaches devices; unsynced work on a deleted record is kept + flagged
    const doomed = await (async () => (await A.all("subjects"))[1])();
    B.net.online = false;
    await B.E.queueChange(SCHOOL, "subjects", "update", { name: "Renamed offline" }, doomed.client_uuid);
    const del = await fetch(baseUrl + "/api/__test__/delete_subject/" + doomed.id,
        { method: "POST", headers: { "X-Device-Id": ctx.credA.device_id, "X-Device-Secret": ctx.credA.device_secret } });
    check("server deleted subject", del.status === 200);
    await sleep(1100);
    await A.sync();
    check("A dropped the deleted subject", !(await A.all("subjects")).find((s) => s.client_uuid === doomed.client_uuid));
    B.net.online = true; await B.sync();
    const kept = await B.db.getRecord(SCHOOL, "subjects", doomed.client_uuid);
    check("B kept its unsynced edit and flagged it", kept && kept._sync.status === "conflict" && /deleted online/.test(kept._sync.last_error), kept && kept._sync);

    console.log(failures ? `\n${failures} FAILED` : "\nengine e2e OK");
    process.exit(failures ? 1 : 0);
})().catch((e) => { console.error("harness error:", e); process.exit(3); });
