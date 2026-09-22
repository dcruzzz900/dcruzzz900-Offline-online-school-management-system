// Usage: node parity.js fixture.json expected.json
// Recomputes broadsheet + result data from a device's synced records with
// static/js/offline-results.js and compares it to what the SERVER computed.
const fs = require("fs");
const path = require("path");
const R = require(path.join(__dirname, "..", "..", "static", "js", "offline-results.js"));
const [fx, ex] = process.argv.slice(2).map((f) => JSON.parse(fs.readFileSync(f, "utf8")));
let failures = 0;
function eq(label, a, b) {
    if (JSON.stringify(a) !== JSON.stringify(b)) { failures++; console.log("MISMATCH", label, "\n  offline:", JSON.stringify(a), "\n  server: ", JSON.stringify(b)); }
}
const d = { ...fx.entities, classId: fx.classId, termId: fx.termId, school_profile: fx.school };
const sheet = R.buildBroadsheet(d);
eq("row order (by position)", sheet.rows.map((r) => r.student.id), ex.broadsheet.map((r) => r.student_id));
sheet.rows.forEach((r, i) => {
    const e = ex.broadsheet[i];
    eq(`total ${r.student.id}`, r.total, e.total);
    eq(`average ${r.student.id}`, r.average, e.average);
    eq(`position ${r.student.id}`, r.position, e.position);
    for (const subj of sheet.subjects) {
        const got = r.scores[subj.id];
        eq(`cell ${r.student.id}/${subj.name}`, got ? { total: got.total, grade: got.grade } : { total: "-", grade: "-" }, e.scores[String(subj.id)]);
    }
});
for (const e of ex.results) {
    const st = fx.entities.students.find((s) => s.id === e.student_id);
    const res = R.buildResult(d, st.client_uuid);
    eq(`result total ${e.student_id}`, res.total, e.total);
    eq(`result average ${e.student_id}`, res.average, e.average);
    eq(`result position ${e.student_id}`, res.position, e.position);
    eq(`result subjects ${e.student_id}`, res.subjects.map((s) => [s.name, s.ca1, s.ca2, s.ca3, s.exam, s.total, s.grade, s.remark]), e.subjects);
    eq(`show_ca3 ${e.student_id}`, res.show_ca3, e.show_ca3);
    eq(`comments ${e.student_id}`, [res.info.teacher_comment || null, res.info.principal_comment || null,
        res.info.teacher_signed_date || null, res.info.principal_signed_date || null], e.info);
    eq(`ratings ${e.student_id}`, res.ratings.map((r) => [r.name, r.category, r.rating]), e.ratings);
    eq(`has result date ${e.student_id}`, !!res.result_date, e.has_result_date);
}
if (ex.cumulative) {
    const cd = { ...d, sessionId: ex.cumulative.sessionId };
    const cum = R.buildCumulativeBroadsheet(cd);
    eq("cumulative terms", cum.terms.map((t) => t.id), ex.cumulative.terms);
    eq("cumulative order", cum.rows.map((r) => r.student.id), ex.cumulative.rows.map((r) => r.student_id));
    cum.rows.forEach((r, i) => {
        const e = ex.cumulative.rows[i];
        eq(`cum average ${r.student.id}`, r.average, e.average);
        eq(`cum position ${r.student.id}`, r.position, e.position);
        for (const subj of cum.subjects) {
            const c = r.subjects[subj.id];
            eq(`cum cell ${r.student.id}/${subj.name}`, { v: c.term_values, a: c.average, g: c.grade }, e.subjects[String(subj.id)]);
        }
    });
}
console.log(failures ? `${failures} mismatches` : `parity OK (${sheet.rows.length} students, ${sheet.subjects.length} subjects)`);
process.exit(failures ? 1 : 0);
