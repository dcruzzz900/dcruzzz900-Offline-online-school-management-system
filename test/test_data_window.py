"""A phone receives only the active session's scores and the active term's attendance (a large
school's full history would be far too much to download), and follows the school when it moves
to a new term - without losing anything unsynced."""
import json
import os
import subprocess
import tempfile
from flask import jsonify
from helpers import fresh_app, new_device, LiveServer, ROOT, device_headers, bootstrap


def _build(m):
    import db
    conn = db.get_db()
    school = conn.execute("SELECT id FROM schools").fetchone()[0]
    cls = conn.execute("SELECT id FROM classes").fetchone()[0]
    session = conn.execute("SELECT id FROM sessions").fetchone()[0]
    t1 = conn.execute("SELECT id FROM terms").fetchone()[0]
    subj = conn.execute("SELECT id FROM subjects ORDER BY id").fetchone()[0]
    students = [r[0] for r in conn.execute("SELECT id FROM students ORDER BY id")]
    conn.execute("INSERT INTO terms (name, session_id, is_active) VALUES ('2nd Term', ?, 0)", (session,))
    t2 = conn.execute("SELECT id FROM terms WHERE name='2nd Term'").fetchone()[0]
    conn.execute("INSERT INTO sessions (school_id, name, is_active) VALUES (?, '2024/2025', 0)", (school,))
    old_session = conn.execute("SELECT id FROM sessions WHERE name='2024/2025'").fetchone()[0]
    conn.execute("INSERT INTO terms (name, session_id, is_active) VALUES ('3rd Term', ?, 0)", (old_session,))
    t_old = conn.execute("SELECT id FROM terms WHERE session_id=?", (old_session,)).fetchone()[0]
    for stu in students:
        for term in (t1, t2, t_old):
            conn.execute("INSERT INTO scores (student_id, subject_id, term_id, ca1, ca2, exam) VALUES (?,?,?,10,10,40)", (stu, subj, term))
        for d in range(1, 6):
            conn.execute("INSERT INTO attendance_records (student_id, class_id, term_id, date, status) VALUES (?,?,?,?,'present')", (stu, cls, t1, f"2026-09-{d:02d}"))
        for d in range(1, 4):
            conn.execute("INSERT INTO attendance_records (student_id, class_id, term_id, date, status) VALUES (?,?,?,?,'present')", (stu, cls, t2, f"2026-12-{d:02d}"))
    conn.commit()
    conn.close()
    return dict(school_id=school, cls=cls, session=session, t1=t1, t2=t2, t_old=t_old, n=len(students))


def test_server_sends_only_the_active_window():
    m, _ = fresh_app()
    f = _build(m)
    dev, cred = new_device(m, "admin", "admin123")
    ents = bootstrap(dev, cred)["entities"]
    assert {r["term_id"] for r in ents["scores"]} == {f["t1"], f["t2"]}          # the old session's are not sent
    assert {r["term_id"] for r in ents["attendance_records"]} == {f["t1"]}       # only the active term's marks
    assert len(ents["attendance_records"]) == 5 * f["n"]
    import db
    conn = db.get_db()                                                             # no active session at all -> the most recently created one
    conn.execute("UPDATE sessions SET is_active=0")
    conn.commit()
    conn.close()
    ents = bootstrap(dev, cred)["entities"]
    assert {r["term_id"] for r in ents["scores"]} == {f["t_old"]}


def test_device_follows_a_term_change_without_losing_unsynced_work():
    m, _ = fresh_app()
    f = _build(m)
    import db

    @m.app.route("/api/__test__/switch_term", methods=["POST"])
    def switch_term():
        c = db.get_db()
        c.execute("UPDATE terms SET is_active=0 WHERE id=?", (f["t1"],))
        c.execute("UPDATE terms SET is_active=1 WHERE id=?", (f["t2"],))
        c.commit()
        c.close()
        return jsonify(ok=True)

    _, cred = new_device(m, "admin", "admin123")
    server = LiveServer(m.app).up()
    try:
        ctxfile = os.path.join(tempfile.mkdtemp(), "ctx.json")
        json.dump({**f, "credA": cred, "scores_current": 2 * f["n"], "att_t1": 5 * f["n"], "att_t2": 3 * f["n"]}, open(ctxfile, "w"))
        out = subprocess.run(["node", os.path.join(ROOT, "tests", "js", "window_e2e.js"), server.base, ctxfile], capture_output=True, text=True, timeout=120)
        assert out.returncode == 0, out.stdout + out.stderr
        assert "window e2e OK" in out.stdout
        conn = db.get_db()
        assert conn.execute("SELECT COUNT(*) FROM attendance_records WHERE date='2026-09-30' AND status='absent'").fetchone()[0] == 1
        conn.close()
    finally:
        server.down()
