// Usage: node xlsx_roundtrip.js write <out.xlsx> | read <in.xlsx>
const fs = require("fs");
const path = require("path");
const X = require(path.join(__dirname, "..", "..", "static", "js", "xlsx-lite.js"));
const [mode, file] = process.argv.slice(2);
(async () => {
    if (mode === "write") {
        const rows = [
            ["# Max marks — CA1: 10, CA2: 10, Exam: 70"],
            ["admission_no", "student_name", "ca1", "ca2", "exam", "total"],
            ["001", "Obi Chinedu <b>&</b> \"Q\"", 9, 8.5, 60, 77.5],
            ["002", "=HYPERLINK(\"http://evil\")", "", 7, 50, 57],
            ["003", "Ünïcödé Ẹ̀kọ́", 10, 10, 70, 90],
        ];
        fs.writeFileSync(file, X.write(rows, "Scores: JSS1A"));
    } else {
        const buf = fs.readFileSync(file);
        const rows = await X.read(buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength));
        process.stdout.write(JSON.stringify(rows));
    }
})().catch((e) => { console.error(e.message); process.exit(2); });
