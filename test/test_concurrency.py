"""Many devices syncing at the same moment (a whole staff room reconnecting): SQLite allows one
writer at a time, and this used to answer some requests with 500 "database is locked" at about
80 devices. Now they wait their turn."""
import json
import threading
import time
import urllib.request
import uuid
from helpers import fresh_app, LiveServer, device_headers


def test_a_crowd_of_devices_syncing_at_once_all_get_through():
    m, _ = fresh_app()
    import db
    db.MAX_DEVICES_PER_USER = 1000
    conn = db.get_db()
    cls = conn.execute("SELECT id FROM classes").fetchone()[0]
    term = conn.execute("SELECT id FROM terms").fetchone()[0]
    school = conn.execute("SELECT id FROM schools").fetchone()[0]
    admin = conn.execute("SELECT id FROM users WHERE username='admin'").fetchone()[0]
    subjects = [r[0] for r in conn.execute("SELECT id FROM subjects")]
    for i in range(4, 124):
        cur = conn.execute("INSERT INTO students (admission_no, first_name, last_name, gender, class_id) VALUES (?,?,?,?,?)",
                           (f"{i:04d}", f"P{i}", f"S{i}", "M", cls))
        conn.execute("INSERT INTO enrollments (student_id, session_id, class_id) SELECT ?, id, ? FROM sessions", (cur.lastrowid, cls))
    students = [r[0] for r in conn.execute("SELECT id FROM students")]
    creds = []
    for i in range(110):
        c = db.issue_device_credential(conn, school, admin, "admin", None, device_label=f"d{i}")
        creds.append({"device_id": c["device_id"], "device_secret": c["secret"]})
    conn.commit()
    conn.close()

    server = LiveServer(m.app).up()
    errors, handled = [], [0]
    lock = threading.Lock()

    def worker(i):
        headers = {**device_headers(creds[i]), "Content-Type": "application/json"}
        for batch in range(4):
            changes = [{"entity": "scores", "client_uuid": uuid.uuid4().hex, "change_id": uuid.uuid4().hex, "op": "upsert",
                        "data": {"student_id": students[(i * 7 + batch * 50 + k) % len(students)], "subject_id": subjects[(i + k) % len(subjects)],
                                 "term_id": term, "ca1": 10, "ca2": 10, "ca3": 0, "exam": 40}} for k in range(50)]
            try:
                req = urllib.request.Request(server.base + "/api/sync/push", data=json.dumps({"changes": changes}).encode(), headers=headers, method="POST")
                body = json.loads(urllib.request.urlopen(req, timeout=90).read())
                with lock:
                    handled[0] += sum(1 for r in body["results"] if r["status"] in ("synced", "conflict"))
                urllib.request.urlopen(urllib.request.Request(server.base + "/api/sync/pull?since=2000-01-01T00:00:00&limit=200", headers=headers), timeout=90).read()
            except Exception as e:
                with lock:
                    errors.append(f"device {i}: {e}")

    try:
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(110)]
        started = time.time()
        [t.start() for t in threads]
        [t.join() for t in threads]
        took = time.time() - started
    finally:
        server.down()
    assert not errors, errors[:5]
    assert handled[0] == 110 * 4 * 50, handled[0]
    assert took < 60, took
