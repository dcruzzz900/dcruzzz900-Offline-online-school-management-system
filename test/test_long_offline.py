"""A teacher's phone that has been offline for weeks: ~800 queued changes, the
device credential expires, other people edit and delete records on the server
in the meantime, then the phone reconnects. Nothing may be lost or silently
overwritten, the expired credential must be handled gracefully, and the work
must reach the server (merged / conflicted / rejected as appropriate)."""
import datetime
import json
import os
import subprocess
import tempfile
import threading
from flask import request, jsonify
from werkzeug.serving import make_server
from helpers import fresh_app, new_device, ROOT


def test_teacher_phone_offline_for_weeks_then_reconnects():
    m, _ = fresh_app()
    import db
    conn = db.get_db()
    school = conn.execute("SELECT id FROM schools").fetchone()[0]
    cls = conn.execute("SELECT id FROM classes").fetchone()[0]
    term = conn.execute("SELECT id FROM terms").fetchone()[0]
    teacher = conn.execute("SELECT id FROM users WHERE username='aokafor'").fetchone()[0]
    subjects = [r[0] for r in conn.execute("SELECT id FROM subjects ORDER BY id LIMIT 4")]
    assert len(subjects) == 4
    for i in range(4, 31):                                    # 30 students: admission numbers 001..030
        cur = conn.execute("INSERT INTO students (admission_no, first_name, last_name, gender, class_id) VALUES (?,?,?,?,?)",
                           (f"{i:03d}", f"Pupil{i}", f"Surname{i:02d}", "M" if i % 2 else "F", cls))
        conn.execute("INSERT INTO enrollments (student_id, session_id, class_id) SELECT ?, id, ? FROM sessions", (cur.lastrowid, cls))
    conn.execute("DELETE FROM class_subjects WHERE class_id=?", (cls,))
    for sb in subjects:
        conn.execute("INSERT INTO class_subjects (class_id, subject_id, teacher_id) VALUES (?,?,?)", (cls, sb, teacher))
    conn.execute("UPDATE classes SET form_teacher_id=? WHERE id=?", (teacher, cls))
    adm = {r["admission_no"]: r["id"] for r in conn.execute("SELECT id, admission_no FROM students")}
    for n in range(2, 9):                                     # existing scores for 002..008 in subject 0
        conn.execute("INSERT INTO scores (student_id, subject_id, term_id, ca1, ca2, exam) VALUES (?,?,?,10,10,30)",
                     (adm[f"{n:03d}"], subjects[0], term))
    conn.commit()
    conn.close()

    credT = credA = None        # enrolled below, after the test-only routes exist (Flask won't add routes once it has served a request)

    def _admin_only():
        from sync_api import resolve_identity
        c = db.get_db()
        ident = resolve_identity(c)
        c.close()
        return ident and ident["role"] == "admin"

    @m.app.route("/api/__test__/weeks_pass", methods=["POST"])
    def weeks_pass():
        assert _admin_only()
        c = db.get_db()
        A = lambda n: c.execute("SELECT id FROM students WHERE admission_no=?", (f"{n:03d}",)).fetchone()[0]
        for n in (2, 3, 4):        # someone fixed the EXAM mark on rows the teacher edited the CA1 of -> mergeable
            c.execute("UPDATE scores SET exam=55 WHERE student_id=? AND subject_id=?", (A(n), subjects[0]))
        for n in (5, 6):           # someone changed the same CA1 to a different value -> true conflict
            c.execute("UPDATE scores SET ca1=12 WHERE student_id=? AND subject_id=?", (A(n), subjects[0]))
        c.execute("INSERT INTO scores (student_id, subject_id, term_id, ca1, ca2, exam) VALUES (?,?,?,0,0,33)",
                  (A(21), subjects[0], term))    # a score for a cell the phone also creates -> clash on 'exam'
        victim = A(11)             # a pupil removed online while the phone still holds edits for them
        for t in ("attendance_records", "scores", "student_term_info", "enrollments"):
            c.execute(f"DELETE FROM {t} WHERE student_id=?", (victim,))
        c.execute("DELETE FROM students WHERE id=?", (victim,))
        c.execute("INSERT INTO students (admission_no, first_name, last_name, gender, class_id) VALUES ('031','New','Arrival','F',?)", (cls,))
        past = (datetime.datetime.utcnow() - datetime.timedelta(days=3)).isoformat(timespec="seconds")
        c.execute("UPDATE device_credentials SET expires_at=? WHERE device_id=?", (past, credT["device_id"]))
        c.commit()
        c.close()
        return jsonify(ok=True)

    @m.app.route("/api/__test__/renew", methods=["POST"])
    def renew():
        assert _admin_only()
        c = db.get_db()
        cred = db.issue_device_credential(c, school, teacher, "teacher", None, device_label="teacher phone",
                                          device_id=request.get_json()["device_id"])
        c.close()
        return jsonify(device_id=cred["device_id"], device_secret=cred["secret"])

    @m.app.route("/api/__test__/verify_weeks", methods=["POST"])
    def verify_weeks():
        assert _admin_only()
        c = db.get_db()
        q = lambda sql, *a: c.execute(sql, a).fetchone()[0]
        A = lambda n: q("SELECT id FROM students WHERE admission_no=?", f"{n:03d}")
        checks, detail = {}, {}
        checks["merged: teacher's CA1 and other person's exam both kept"] = all(
            (q("SELECT ca1 FROM scores WHERE student_id=? AND subject_id=?", A(n), subjects[0]),
             q("SELECT exam FROM scores WHERE student_id=? AND subject_id=?", A(n), subjects[0])) == (18, 55) for n in (2, 3, 4))
        checks["conflict: other person's CA1 not overwritten"] = all(
            q("SELECT ca1 FROM scores WHERE student_id=? AND subject_id=?", A(n), subjects[0]) == 12 for n in (5, 6))
        checks["conflict cell (same exam field) kept the server value"] = q(
            "SELECT exam FROM scores WHERE student_id=? AND subject_id=?", A(21), subjects[0]) == 33
        checks["3 conflicts recorded for a person to resolve"] = q("SELECT COUNT(*) FROM sync_conflicts WHERE resolved=0") == 3
        detail["conflicts"] = q("SELECT COUNT(*) FROM sync_conflicts WHERE resolved=0")
        untouched = [n for n in range(1, 31) if n not in (5, 6, 11, 21)]
        checks["every other class-subject score row exists"] = all(
            q("SELECT COUNT(*) FROM scores WHERE student_id=?", A(n)) == 4 for n in untouched)
        att = q("SELECT COUNT(*) FROM attendance_records WHERE class_id=? AND date LIKE '2026-08-%'", cls)
        checks["attendance: 29 pupils x 20 days (the removed pupil's rows refused)"] = att == 29 * 20
        detail["attendance"] = att
        checks["no orphan rows for the removed pupil"] = q(
            "SELECT COUNT(*) FROM scores WHERE student_id NOT IN (SELECT id FROM students)") == 0 and q(
            "SELECT COUNT(*) FROM attendance_records WHERE student_id NOT IN (SELECT id FROM students)") == 0
        checks["report-card days follow the synced roll calls"] = q(
            "SELECT days_school_opened FROM student_term_info WHERE student_id=?", A(1)) == 20
        who = {r[0] for r in c.execute("SELECT DISTINCT user_id FROM change_audit WHERE outcome IN ('applied','merged')")}
        checks["everything is attributed to the teacher's account"] = who == {teacher}
        checks["score history kept for the offline edits"] = q("SELECT COUNT(*) FROM score_history WHERE source='offline-sync'") > 100
        c.close()
        return jsonify(checks=checks, detail=detail)

    @m.app.route("/api/__test__/bulk_changes", methods=["POST"])
    def bulk_changes():
        assert _admin_only()
        c = db.get_db()
        stu = c.execute("SELECT id FROM students WHERE class_id=? LIMIT 5", (cls,)).fetchall()
        n = 0
        for sid in [r[0] for r in stu]:
            for day in range(1, 300):
                c.execute("INSERT OR IGNORE INTO attendance_records (student_id, class_id, term_id, date, status) VALUES (?,?,?,?,?)",
                          (sid, cls, term, f"2027-{1 + day // 28:02d}-{1 + day % 28:02d}", "present"))
                n += 1
        c.commit()
        total = c.execute("SELECT COUNT(*) FROM attendance_records").fetchone()[0]
        c.close()
        return jsonify(attendance_rows=total)

    _, credT = new_device(m, "aokafor", "teacher123", "teacher phone")
    _, credA = new_device(m, "admin", "admin123", "admin tablet")
    server = make_server("127.0.0.1", 0, m.app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        ctxfile = os.path.join(tempfile.mkdtemp(), "ctx.json")
        json.dump({"school_id": school, "cls": cls, "term": term, "credT": credT, "credA": credA}, open(ctxfile, "w"))
        out = subprocess.run(["node", os.path.join(ROOT, "tests", "js", "long_offline_e2e.js"),
                              f"http://127.0.0.1:{server.server_port}", ctxfile], capture_output=True, text=True, timeout=300)
        if os.environ.get("SHOW_E2E"):
            print(out.stdout)
        assert out.returncode == 0, out.stdout + out.stderr
        assert "long-offline e2e OK" in out.stdout
    finally:
        server.shutdown()
