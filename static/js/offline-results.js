/*
 * Offline results engine.
 *
 * Everything a result sheet or broadsheet needs is worked out here, in the
 * browser, from the records already synced into this device's local database
 * — no server round trip. It is deliberately a pure module (plain data in,
 * plain data / HTML strings out, no IndexedDB, no DOM) so it can be tested in
 * Node against the same numbers the server produces.
 *
 * The arithmetic mirrors app.py exactly, so a result sheet printed offline
 * matches the one the server would print for the same data:
 *   - subject total  = round(CA1 + CA2 + CA3 + Exam, 2)          (compute_total)
 *   - grade          = first grade band with min <= total <= max  (grade_for)
 *   - overall total  = sum of subject totals; average = round(total / subjects
 *                      written, 2)                                (build_broadsheet_data)
 *   - position       = rank by overall total, students ordered by last name
 *                      first so ties keep a stable order
 *   - a student's class for a term comes from their enrollment in that term's
 *     session when there is one, else their current class.
 */
const OfflineResults = (function () {
    // ---- numbers ---------------------------------------------------------

    function num(v) {
        const n = parseFloat(v);
        return Number.isFinite(n) ? n : 0;
    }

    // Python's round(x, 2) rounds an exact tie to the even hundredth; toFixed
    // rounds it up. Exact ties only occur for multiples of 1/8 (0.125, 0.375…).
    function round2(x) {
        const eighths = x * 8;
        if (Number.isInteger(eighths) && Math.abs(eighths % 2) === 1) {
            const h = Math.floor(x * 100);
            return (h % 2 === 0 ? h : h + 1) / 100;
        }
        return Number(x.toFixed(2));
    }

    function computeTotal(ca1, ca2, exam, ca3) {
        return round2(num(ca1) + num(ca2) + num(ca3) + num(exam));
    }

    function ca3Enabled(config) {
        return !!(config && num(config.ca3_max) > 0);
    }

    function gradeFor(total, scale) {
        const bands = (scale || []).slice().sort((a, b) => (a.id || 0) - (b.id || 0));
        for (const b of bands) {
            if (total >= num(b.min_score) && total <= num(b.max_score)) return { grade: b.grade, remark: b.remark || "" };
        }
        return { grade: "-", remark: "-" };
    }

    const cmp = (a, b) => (a < b ? -1 : a > b ? 1 : 0);   // binary order, like SQLite's default

    // ---- broadsheet / result data ---------------------------------------

    function activeRows(list) {
        return (list || []).filter((r) => !r.is_deleted);
    }

    function classForTerm(student, sessionId, enrollments) {
        const e = (enrollments || []).find((x) => x.student_id === student.id && x.session_id === sessionId);
        return e ? e.class_id : student.class_id;
    }

    /**
     * @param d {students, subjects, class_subjects, scores, enrollments, terms,
     *           grading_config, grade_scale, classId, termId}
     */
    function buildBroadsheet(d) {
        const term = activeRows(d.terms).find((t) => t.id === d.termId);
        const sessionId = term ? term.session_id : null;
        const subjectById = new Map(activeRows(d.subjects).map((s) => [s.id, s]));
        const subjects = activeRows(d.class_subjects)
            .filter((cs) => cs.class_id === d.classId)
            .map((cs) => subjectById.get(cs.subject_id))
            .filter(Boolean)
            .sort((a, b) => cmp(a.name, b.name));

        const students = activeRows(d.students)
            .filter((s) => s.id && s.is_active !== 0 && classForTerm(s, sessionId, activeRows(d.enrollments)) === d.classId)
            .sort((a, b) => cmp(a.last_name, b.last_name));

        const scoreKey = (sid, subj, t) => `${sid}:${subj}:${t}`;
        const scores = new Map(activeRows(d.scores).map((x) => [scoreKey(x.student_id, x.subject_id, x.term_id), x]));

        const rows = students.map((st) => {
            const per = {};
            let total = 0, count = 0;
            for (const subj of subjects) {
                const sc = scores.get(scoreKey(st.id, subj.id, d.termId));
                if (sc) {
                    const t = computeTotal(sc.ca1, sc.ca2, sc.exam, sc.ca3);
                    const g = gradeFor(t, d.grade_scale);
                    per[subj.id] = { total: t, grade: g.grade, remark: g.remark, ca1: num(sc.ca1), ca2: num(sc.ca2), ca3: num(sc.ca3), exam: num(sc.exam) };
                    total += t;
                    count += 1;
                } else {
                    per[subj.id] = null;
                }
            }
            return { student: st, scores: per, total, count, average: count ? round2(total / count) : 0 };
        });
        rows.sort((a, b) => b.total - a.total);           // stable, like Python's sort
        rows.forEach((r, i) => { r.position = i + 1; });
        return { subjects, rows, term };
    }

    const TERM_ORDER = { "1st Term": 1, "2nd Term": 2, "3rd Term": 3 };

    // Mirror of app.py build_cumulative_broadsheet_data: for each subject, the average of
    // the totals from every term in the session that has a score (a term with no score
    // for that subject isn't counted), then students ranked by overall cumulative average.
    function buildCumulativeBroadsheet(d) {
        const terms = activeRows(d.terms).filter((t) => t.session_id === d.sessionId)
            .sort((a, b) => (TERM_ORDER[a.name] || 99) - (TERM_ORDER[b.name] || 99) || a.id - b.id);
        const subjectById = new Map(activeRows(d.subjects).map((s) => [s.id, s]));
        const subjects = activeRows(d.class_subjects).filter((cs) => cs.class_id === d.classId)
            .map((cs) => subjectById.get(cs.subject_id)).filter(Boolean).sort((a, b) => cmp(a.name, b.name));
        const students = activeRows(d.students)
            .filter((s) => s.id && s.is_active !== 0 && classForTerm(s, d.sessionId, activeRows(d.enrollments)) === d.classId)
            .sort((a, b) => cmp(a.last_name, b.last_name));
        const scores = new Map(activeRows(d.scores).map((x) => [`${x.student_id}:${x.subject_id}:${x.term_id}`, x]));
        const rows = students.map((st) => {
            const per = {};
            let overallTotal = 0, overallCount = 0;
            for (const subj of subjects) {
                const termValues = [];
                const present = [];
                for (const t of terms) {
                    const sc = scores.get(`${st.id}:${subj.id}:${t.id}`);
                    if (sc) { const v = computeTotal(sc.ca1, sc.ca2, sc.exam, sc.ca3); termValues.push(v); present.push(v); }
                    else termValues.push(null);
                }
                if (present.length) {
                    const avg = round2(present.reduce((a, b) => a + b, 0) / present.length);
                    per[subj.id] = { term_values: termValues, average: avg, grade: gradeFor(avg, d.grade_scale).grade };
                    overallTotal += avg; overallCount += 1;
                } else {
                    per[subj.id] = { term_values: termValues, average: "-", grade: "-" };
                }
            }
            return { student: st, subjects: per, average: overallCount ? round2(overallTotal / overallCount) : 0 };
        });
        rows.sort((a, b) => b.average - a.average);
        rows.forEach((r, i) => { r.position = i + 1; });
        return { subjects, terms, rows };
    }

    function cumulativeHtml(sheet, cls, profile, logoDataUrl, sessionName) {
        const head = sheet.subjects.map((sub) => `<th colspan="${sheet.terms.length + 1}">${esc(sub.name)}</th>`).join("");
        const sub = sheet.subjects.map(() => sheet.terms.map((t) => `<th>${esc(String(t.name).replace(" Term", ""))}</th>`).join("") + "<th>Avg</th>").join("");
        const body = sheet.rows.map((r) => `<tr><td>${r.position}</td><td class="l">${esc(fullName(r.student))}</td>${
            sheet.subjects.map((s) => { const c = r.subjects[s.id]; return c.term_values.map((v) => `<td>${v === null ? "-" : esc(v)}</td>`).join("") + `<td>${esc(c.average)} ${esc(c.grade)}</td>`; }).join("")
        }<td>${esc(r.average)}</td></tr>`).join("");
        return `<div class="sheet">${headerHtml(profile, logoDataUrl, "Cumulative Broadsheet", `${cls ? cls.name : ""} — ${sessionName || ""}`)}
            <table><tr><th rowspan="2">Pos.</th><th rowspan="2" class="l">Student</th>${head}<th rowspan="2">Overall</th></tr><tr>${sub}</tr>${body}</table></div>`;
    }

    function buildResult(d, studentUuid) {
        const sheet = buildBroadsheet(d);
        const row = sheet.rows.find((r) => r.student.client_uuid === studentUuid);
        if (!row) return null;
        const student = row.student;
        const cls = activeRows(d.classes).find((c) => c.id === d.classId);
        const subjects = sheet.subjects.map((subj) => {
            const s = row.scores[subj.id];
            return s
                ? { name: subj.name, ...s }
                : { name: subj.name, ca1: "-", ca2: "-", ca3: "-", exam: "-", total: "-", grade: "-", remark: "-" };
        });
        const storedInfo = activeRows(d.student_term_info).find((i) => i.student_id === student.id && i.term_id === d.termId) || {};
        const info = { ...storedInfo };
        // Schools that switched on auto-generated comments get the generated text
        // instead of whatever is stored, exactly as the online result page does.
        const flags = d.school_profile || {};
        if (flags.auto_teacher_comment || flags.auto_principal_comment) {
            const remark = gradeFor(row.average, d.grade_scale).remark;
            if (flags.auto_teacher_comment) info.teacher_comment = bankComment(remark, row.average, row.count);
            if (flags.auto_principal_comment) info.principal_comment = bankComment(remark, row.average, row.count);
        }
        const traitById = new Map(activeRows(d.skill_traits).map((t) => [t.id, t]));
        const ratings = activeRows(d.student_skill_ratings)
            .filter((r) => r.student_id === student.id && r.term_id === d.termId && traitById.has(r.trait_id))
            .sort((a, b) => (a.id || 0) - (b.id || 0))
            .map((r) => ({ name: traitById.get(r.trait_id).name, category: traitById.get(r.trait_id).category, rating: r.rating }));
        // Days open/present/absent: from the roll-call records themselves
        // (they may not have synced into student_term_info yet).
        const att = activeRows(d.attendance_records).filter((a) => a.student_id === student.id && a.term_id === d.termId);
        const days = att.length
            ? { opened: att.length, present: att.filter((a) => a.status === "present").length, absent: att.filter((a) => a.status === "absent").length }
            : { opened: info.days_school_opened || 0, present: info.days_present || 0, absent: info.days_absent || 0 };
        return {
            student, class_row: cls, term: sheet.term, subjects,
            total: row.total, average: row.average, position: row.position, class_size: sheet.rows.length,
            subjects_written: row.count, show_ca3: ca3Enabled(Array.isArray(d.grading_config) ? d.grading_config[0] : d.grading_config),
            info, days, ratings,
            result_date: flags.show_result_date ? dmy(todayIso()) : null,
        };
    }

    // ---- auto comments (mirror of db.py _COMMENT_BANK / _bank_comment) ----
    const COMMENT_BANK = {
        "excellent": "Excellent performance. Keep it up.",
        "very good": "Very good performance. Keep it up.",
        "good": "Good performance. More effort is encouraged.",
        "fair": "Satisfactory performance. There is room for improvement.",
        "pass": "Needs more effort and consistent study.",
        "fail": "Significant improvement is needed.",
    };

    function bankComment(remark, average, subjectsWritten) {
        if (!subjectsWritten) return "No scores recorded yet for this term.";
        const text = COMMENT_BANK[String(remark || "").trim().toLowerCase()];
        if (text) return text;
        if (average >= 70) return COMMENT_BANK["excellent"];
        if (average >= 60) return COMMENT_BANK["very good"];
        if (average >= 50) return COMMENT_BANK["good"];
        if (average >= 45) return COMMENT_BANK["fair"];
        if (average >= 40) return COMMENT_BANK["pass"];
        return COMMENT_BANK["fail"];
    }

    // 'YYYY-MM-DD' -> 'DD/MM/YYYY' (anything else is returned unchanged, like db.format_dmy)
    function dmy(value) {
        const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value || "").trim());
        return m ? `${m[3]}/${m[2]}/${m[1]}` : (value || "");
    }

    function todayIso() {
        const d = new Date();
        return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    }

    // ---- html ------------------------------------------------------------

    function esc(v) {
        return String(v === null || v === undefined ? "" : v)
            .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
    }

    function fullName(s) {
        return [s.last_name, s.first_name, s.other_names].filter(Boolean).join(" ");
    }

    function ordinal(n) {
        if (!Number.isFinite(n)) return String(n);
        const v = n % 100;
        const suffix = v >= 11 && v <= 13 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" }[n % 10] || "th");
        return n + suffix;
    }

    const PRINT_CSS = `
        body { font-family: Helvetica, Arial, sans-serif; color:#111; margin:0; }
        .sheet { padding: 14mm 12mm; page-break-after: always; }
        .sheet:last-child { page-break-after: auto; }
        .head { text-align:center; margin-bottom: 6mm; }
        .head img { max-height: 22mm; }
        .head h1 { font-size: 18pt; margin: 2mm 0 0; }
        .head h2 { font-size: 12pt; margin: 1mm 0 0; font-weight: normal; color:#333; }
        table { border-collapse: collapse; width: 100%; margin: 3mm 0; font-size: 10pt; }
        th, td { border: 1px solid #555; padding: 1.5mm 2mm; text-align: center; }
        th { background: #182a44; color: #fff; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
        td.l, th.l { text-align: left; }
        .info td { border: none; text-align: left; padding: 0.8mm 2mm; }
        .sum { display:flex; gap: 8mm; font-size: 10pt; margin: 2mm 0; }
        .comment { border: 1px solid #555; padding: 2mm; margin: 2mm 0; font-size: 10pt; min-height: 10mm; }
        .foot { font-size: 8pt; color:#666; margin-top: 4mm; text-align:center; }
        @page { size: A4; margin: 8mm; }
        @media print { .no-print { display:none; } }
    `;

    function headerHtml(profile, logoDataUrl, title, subtitle) {
        return `<div class="head">${logoDataUrl ? `<img src="${esc(logoDataUrl)}" alt="">` : ""}
            <h1>${esc((profile && profile.name) || "School")}</h1>
            <h2>${esc(title)}</h2>${subtitle ? `<h2>${esc(subtitle)}</h2>` : ""}</div>`;
    }

    function resultSheetHtml(res, profile, logoDataUrl, opts) {
        opts = opts || {};
        const s = res.student;
        const term = res.term || {};
        const ca3 = res.show_ca3;
        const rowsHtml = res.subjects.map((x) => `<tr><td class="l">${esc(x.name)}</td><td>${esc(x.ca1)}</td><td>${esc(x.ca2)}</td>${ca3 ? `<td>${esc(x.ca3)}</td>` : ""}<td>${esc(x.exam)}</td><td>${esc(x.total)}</td><td>${esc(x.grade)}</td><td class="l">${esc(x.remark)}</td></tr>`).join("");
        const pos = typeof res.position === "number" ? `${ordinal(res.position)} of ${res.class_size}` : "-";
        const pct = res.days.opened ? Math.round((res.days.present / res.days.opened) * 1000) / 10 : 0;
        return `<div class="sheet">
            ${headerHtml(profile, logoDataUrl, "Terminal Report Sheet", `${term.name || ""}`)}
            <table class="info"><tr>
                <td><b>Name:</b> ${esc(fullName(s))}</td><td><b>Admission No.:</b> ${esc(s.admission_no)}</td></tr><tr>
                <td><b>Class:</b> ${esc(res.class_row ? res.class_row.name : "")}</td><td><b>Gender:</b> ${esc(s.gender || "")}</td></tr></table>
            <table><tr><th class="l">Subject</th><th>CA1</th><th>CA2</th>${ca3 ? "<th>CA3</th>" : ""}<th>Exam</th><th>Total</th><th>Grade</th><th class="l">Remark</th></tr>${rowsHtml}</table>
            <div class="sum"><span><b>Total:</b> ${esc(res.total)}</span><span><b>Average:</b> ${esc(res.average)}</span><span><b>Position:</b> ${esc(pos)}</span><span><b>Subjects:</b> ${esc(res.subjects_written)}</span></div>
            <div class="sum"><span><b>Days open:</b> ${esc(res.days.opened)}</span><span><b>Present:</b> ${esc(res.days.present)}</span><span><b>Absent:</b> ${esc(res.days.absent)}</span><span><b>Attendance:</b> ${esc(pct)}%</span></div>
            ${res.ratings && res.ratings.length ? `<table><tr><th class="l">Psychomotor / Affective trait</th><th>Category</th><th>Rating (1-5)</th></tr>${
                res.ratings.map((r) => `<tr><td class="l">${esc(r.name)}</td><td>${esc(String(r.category || "").replace(/^./, (c) => c.toUpperCase()))}</td><td>${esc(r.rating)}</td></tr>`).join("")}</table>` : ""}
            <div class="comment"><b>Teacher's comment:</b> ${esc(res.info.teacher_comment || "")}</div>
            <div class="sum"><span>Teacher's signature: ______________</span><span>Date: ${esc(res.info.teacher_signed_date ? dmy(res.info.teacher_signed_date) : "______________")}</span></div>
            <div class="comment"><b>Principal's comment:</b> ${esc(res.info.principal_comment || "")}</div>
            <div class="sum"><span>Principal's signature: ______________</span><span>Date: ${esc(res.info.principal_signed_date ? dmy(res.info.principal_signed_date) : "______________")}</span></div>
            ${res.result_date ? `<div class="sum"><span>Date of result: ${esc(res.result_date)}</span></div>` : ""}
            ${opts.unsyncedNote ? `<div class="foot">${esc(opts.unsyncedNote)}</div>` : ""}
        </div>`;
    }

    function broadsheetHtml(sheet, cls, profile, logoDataUrl, showCa3Unused) {
        const head = sheet.subjects.map((sub) => `<th>${esc(sub.name)}</th>`).join("");
        const body = sheet.rows.map((r) => `<tr><td>${r.position}</td><td class="l">${esc(fullName(r.student))}</td>${
            sheet.subjects.map((sub) => { const x = r.scores[sub.id]; return `<td>${x ? esc(x.total) + " " + esc(x.grade) : "-"}</td>`; }).join("")
        }<td>${esc(r.total)}</td><td>${esc(r.average)}</td></tr>`).join("");
        return `<div class="sheet">${headerHtml(profile, logoDataUrl, "Broadsheet", `${cls ? cls.name : ""} — ${(sheet.term && sheet.term.name) || ""}`)}
            <table><tr><th>Pos.</th><th class="l">Student</th>${head}<th>Total</th><th>Average</th></tr>${body}</table></div>`;
    }

    function documentHtml(bodyHtml, title) {
        return `<!DOCTYPE html><html><head><meta charset="utf-8"><title>${esc(title)}</title><style>${PRINT_CSS}</style></head><body>${bodyHtml}</body></html>`;
    }

    // ---- CSV -------------------------------------------------------------

    function csvCell(v) {
        let s = v === null || v === undefined ? "" : String(v);
        // Spreadsheet formula injection: a text cell starting with = + @ (or a
        // minus that isn't a plain negative number) would be run as a formula.
        if (/^[=+@]/.test(s) || (/^-/.test(s) && !/^-?\d+(\.\d+)?$/.test(s))) s = "'" + s;
        return /[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
    }

    function toCsv(rows) {
        return "\uFEFF" + rows.map((r) => r.map(csvCell).join(",")).join("\r\n") + "\r\n";
    }

    function parseCsv(text) {
        text = String(text || "").replace(/^\uFEFF/, "");
        const rows = [];
        let row = [], cell = "", inQuotes = false;
        for (let i = 0; i < text.length; i++) {
            const c = text[i];
            if (inQuotes) {
                if (c === '"') { if (text[i + 1] === '"') { cell += '"'; i++; } else inQuotes = false; }
                else cell += c;
            } else if (c === '"') inQuotes = true;
            else if (c === ",") { row.push(cell); cell = ""; }
            else if (c === "\n" || c === "\r") {
                if (c === "\r" && text[i + 1] === "\n") i++;
                row.push(cell); cell = "";
                rows.push(row); row = [];
            } else cell += c;
        }
        if (cell !== "" || row.length) { row.push(cell); rows.push(row); }
        return rows.filter((r) => r.some((c) => String(c).trim() !== ""));
    }

    // Turns rows (array of arrays, first non-comment row = header) into objects.
    function rowsToObjects(rows) {
        let start = 0;
        while (start < rows.length && String(rows[start][0] || "").trim().startsWith("#")) start++;
        if (start >= rows.length) return { header: [], objects: [] };
        const header = rows[start].map((h) => String(h).trim().toLowerCase());
        const objects = rows.slice(start + 1).map((r, i) => {
            const o = { __row: start + i + 2 };
            header.forEach((h, idx) => { o[h] = r[idx] === undefined ? "" : String(r[idx]).trim(); });
            return o;
        });
        return { header, objects };
    }

    function scoresExportRows(students, existing, config) {
        const ca3 = ca3Enabled(config);
        const maxes = `# Max marks — CA1: ${config.ca1_max}, CA2: ${config.ca2_max}, ${ca3 ? `CA3: ${config.ca3_max}, ` : ""}Exam: ${config.exam_max}`;
        const out = [[maxes], ["admission_no", "student_name", "ca1", "ca2"].concat(ca3 ? ["ca3"] : [], ["exam", "total"])];
        for (const s of students) {
            const sc = existing.get(s.id);
            out.push([s.admission_no, fullName(s), sc ? sc.ca1 : "", sc ? sc.ca2 : ""].concat(
                ca3 ? [sc ? num(sc.ca3) : ""] : [],
                [sc ? sc.exam : "", sc ? computeTotal(sc.ca1, sc.ca2, sc.exam, sc.ca3) : ""]));
        }
        return out;
    }

    /** Validates an uploaded scores file the way the server will. */
    function planScoreImport(rows, students, config) {
        const { header, objects } = rowsToObjects(rows);
        if (!header.includes("admission_no")) return { updates: [], skipped: ["The file needs an admission_no column (use the exported template)."] };
        const ca3 = ca3Enabled(config);
        const byAdm = new Map(students.map((s) => [String(s.admission_no).trim(), s]));
        const updates = [], skipped = [];
        for (const o of objects) {
            const st = byAdm.get(o.admission_no);
            if (!st) { skipped.push(`Row ${o.__row}: no student with admission no. '${o.admission_no}' in this class`); continue; }
            const vals = { ca1: o.ca1, ca2: o.ca2, ca3: ca3 ? o.ca3 : "0", exam: o.exam };
            const nums = {};
            let bad = false;
            for (const k of Object.keys(vals)) {
                const raw = vals[k] === undefined || vals[k] === "" ? "0" : vals[k];
                if (!/^-?\d+(\.\d+)?$/.test(String(raw).trim())) { skipped.push(`Row ${o.__row} (${fullName(st)}): ${k.toUpperCase()} must be a number`); bad = true; break; }
                nums[k] = parseFloat(raw);
            }
            if (bad) continue;
            const limits = { ca1: num(config.ca1_max), ca2: num(config.ca2_max), ca3: num(config.ca3_max), exam: num(config.exam_max) };
            const errs = Object.keys(nums).filter((k) => nums[k] < 0 || nums[k] > limits[k]).map((k) => `${k.toUpperCase()} ${nums[k]} is outside 0–${limits[k]}`);
            if (errs.length) { skipped.push(`Row ${o.__row} (${fullName(st)}): ${errs.join("; ")}`); continue; }
            updates.push({ student: st, ...nums });
        }
        return { updates, skipped };
    }

    /** Validates an uploaded student list; classes must already exist and be synced. */
    function planStudentImport(rows, classes, existingStudents) {
        const { header, objects } = rowsToObjects(rows);
        const required = ["admission_no", "first_name", "last_name", "class_name"];
        const missing = required.filter((h) => !header.includes(h));
        if (missing.length) return { creates: [], skipped: [`The file must have these columns: ${required.join(", ")}.`] };
        const classByName = new Map(activeRows(classes).filter((c) => c.id).map((c) => [String(c.name).trim().toLowerCase(), c]));
        const taken = new Set(activeRows(existingStudents).map((s) => `${s.class_id}|${String(s.admission_no).trim()}`));
        const creates = [], skipped = [];
        for (const o of objects) {
            if (!(o.admission_no && o.first_name && o.last_name && o.class_name)) { skipped.push(`Row ${o.__row}: missing required field(s)`); continue; }
            const cls = classByName.get(o.class_name.toLowerCase());
            if (!cls) { skipped.push(`Row ${o.__row}: class '${o.class_name}' doesn't exist (or hasn't synced yet)`); continue; }
            const key = `${cls.id}|${o.admission_no}`;
            if (taken.has(key)) { skipped.push(`Row ${o.__row}: admission no. '${o.admission_no}' is already used in ${o.class_name}`); continue; }
            taken.add(key);
            const g = (o.gender || "").toUpperCase().slice(0, 1);
            creates.push({
                admission_no: o.admission_no, first_name: o.first_name, last_name: o.last_name,
                other_names: o.other_names || null, gender: g === "M" || g === "F" ? g : null,
                class_id: cls.id, date_of_birth: o.date_of_birth || null, religion: o.religion || null,
                parent_name: o.parent_name || null, parent_address: o.parent_address || null,
                parent_email: o.parent_email || null, parent_phone: o.parent_phone || null, is_active: 1,
            });
        }
        return { creates, skipped };
    }

    const api = {
        num, round2, bankComment, dmy, computeTotal, ca3Enabled, gradeFor, buildBroadsheet, buildResult,
        resultSheetHtml, broadsheetHtml, buildCumulativeBroadsheet, cumulativeHtml, documentHtml, fullName, esc,
        csvCell, toCsv, parseCsv, rowsToObjects, scoresExportRows, planScoreImport, planStudentImport,
    };
    if (typeof module !== "undefined" && module.exports) module.exports = api;
    return api;
})();
