"""Runs the real client sync engine (Node) against a live Flask server."""
import json
import os
import subprocess
import tempfile
import threading
from werkzeug.serving import make_server
from helpers import fresh_app, new_device, ROOT


def test_client_engine_against_live_server():
    m, _ = fresh_app()
    import db
    conn = db.get_db()
    ids = dict(
        school_id=conn.execute("SELECT id FROM schools").fetchone()[0],
        cls=conn.execute("SELECT id FROM classes").fetchone()[0],
        term=conn.execute("SELECT id FROM terms").fetchone()[0],
        subject=conn.execute("SELECT id FROM subjects ORDER BY id").fetchone()[0],
        student=conn.execute("SELECT id FROM students ORDER BY id").fetchone()[0],
    )
    conn.execute("INSERT INTO scores (student_id, subject_id, term_id, ca1, ca2, exam) VALUES (?,?,?,10,10,40)",
                 (ids["student"], ids["subject"], ids["term"]))
    conn.commit()
    conn.close()

    # test-only route (registered only in this process) to simulate an admin deleting online
    @m.app.route("/api/__test__/delete_subject/<int:sid>", methods=["POST"])
    def _delete_subject(sid):
        c = db.get_db()
        c.execute("DELETE FROM class_subjects WHERE subject_id=?", (sid,))
        c.execute("DELETE FROM subjects WHERE id=?", (sid,))
        c.commit()
        c.close()
        return "ok"

    _, credA = new_device(m, "admin", "admin123", "A")
    _, credB = new_device(m, "admin", "admin123", "B")
    server = make_server("127.0.0.1", 0, m.app, threaded=True)
    port = server.server_port
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        ctxfile = os.path.join(tempfile.mkdtemp(), "ctx.json")
        json.dump({**ids, "credA": credA, "credB": credB}, open(ctxfile, "w"))
        out = subprocess.run(["node", os.path.join(ROOT, "tests", "js", "engine_e2e.js"), f"http://127.0.0.1:{port}", ctxfile],
                             capture_output=True, text=True, timeout=120)
        assert out.returncode == 0, out.stdout + out.stderr
        assert "engine e2e OK" in out.stdout
    finally:
        server.shutdown()
