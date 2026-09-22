"""Shared test bootstrap: every test process gets its own throw-away
DATA_DIR (so tests never touch a real school.db) and a seeded demo school
(admin/admin123, teacher aokafor/teacher123, class JSS1A, 3 students)."""
import os
import sys
import tempfile
import importlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def fresh_app():
    tmp = tempfile.mkdtemp(prefix="srs_test_")
    os.environ["DATA_DIR"] = tmp
    os.environ.pop("SKIP_DEMO_SEED", None)
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    for mod in ("db", "sync_api", "app"):
        sys.modules.pop(mod, None)
    app_mod = importlib.import_module("app")
    app_mod.app.config["TESTING"] = True
    return app_mod, tmp


def login(client, username, password):
    """Log in through the real /login form (CSRF token pulled from the session)."""
    client.get("/login")
    with client.session_transaction() as s:
        token = s.get("_csrf_token")
    if not token:
        client.get("/login")
        with client.session_transaction() as s:
            token = s["_csrf_token"]
    return client.post("/login", data={"username": username, "password": password, "csrf_token": token},
                       follow_redirects=False)


def csrf(client):
    with client.session_transaction() as s:
        if "_csrf_token" not in s:
            s["_csrf_token"] = "test-token"
        return s["_csrf_token"]


def enroll(client, label="test-device", device_id=None):
    body = {"device_label": label}
    if device_id:
        body["device_id"] = device_id
    r = client.post("/api/offline/enroll", json=body, headers={"X-CSRF-Token": csrf(client)})
    assert r.status_code == 200, r.data
    return r.get_json()


def device_headers(cred):
    return {"X-Device-Id": cred["device_id"], "X-Device-Secret": cred["device_secret"]}


def make_school(app_mod, name="School B", admin_username="adminb", password="pass-b-123"):
    """Insert a second, fully separate school (admin, session/term, class,
    subject, one student) straight into the DB and return its ids."""
    import db
    from werkzeug.security import generate_password_hash
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO schools (name) VALUES (?)", (name,))
    sid = cur.lastrowid
    cur.execute("INSERT INTO users (school_id, name, username, password_hash, role) VALUES (?,?,?,?,?)",
                (sid, f"{name} Admin", admin_username, generate_password_hash(password), "admin"))
    admin_id = cur.lastrowid
    cur.execute("INSERT INTO sessions (school_id, name, is_active) VALUES (?,?,1)", (sid, "2025/2026"))
    session_id = cur.lastrowid
    cur.execute("INSERT INTO terms (name, session_id, is_active) VALUES ('1st Term', ?, 1)", (session_id,))
    term_id = cur.lastrowid
    conn.commit()
    db.seed_school_defaults(conn, sid)
    cur.execute("INSERT INTO classes (school_id, name) VALUES (?, 'SS1A')", (sid,))
    class_id = cur.lastrowid
    cur.execute("INSERT INTO subjects (school_id, name) VALUES (?, 'Physics')", (sid,))
    subject_id = cur.lastrowid
    cur.execute("INSERT INTO students (admission_no, first_name, last_name, gender, class_id) VALUES ('B001','Bola','Ade','F',?)",
                (class_id,))
    student_id = cur.lastrowid
    conn.commit()
    conn.close()
    return dict(school_id=sid, admin_id=admin_id, term_id=term_id, class_id=class_id,
                subject_id=subject_id, student_id=student_id,
                admin=(admin_username, password))


def new_device(app_mod, username, password, label="dev"):
    """Log a user in on a throw-away client, enroll a device, return (client_with_device_headers, cred)."""
    c = app_mod.app.test_client()
    r = login(c, username, password)
    assert r.status_code == 302, "login failed"
    cred = enroll(c, label)
    dev = app_mod.app.test_client()
    return dev, cred


def push(dev, cred, changes):
    r = dev.post("/api/sync/push", json={"changes": changes}, headers=device_headers(cred))
    assert r.status_code == 200, r.data
    return r.get_json()["results"]


def bootstrap(dev, cred):
    r = dev.get("/api/sync/bootstrap", headers=device_headers(cred))
    assert r.status_code == 200, r.data
    return r.get_json()


def pull(dev, cred, since):
    r = dev.get(f"/api/sync/pull?since={since}", headers=device_headers(cred))
    assert r.status_code == 200, r.data
    return r.get_json()


import uuid as _uuid


def change(entity, data, client_uuid=None, base_updated_at=None, base_data=None, client_ts=None, op="upsert"):
    return {"entity": entity, "client_uuid": client_uuid or str(_uuid.uuid4()),
            "change_id": str(_uuid.uuid4()), "op": op,
            "base_updated_at": base_updated_at, "base_data": base_data,
            "client_ts": client_ts, "data": data}


class LiveServer:
    """The Flask app on a real localhost port that can be switched off and back
    on (same port) - so "offline" in a browser test means connections are
    actually refused, including the ones the service worker makes. (Playwright's
    own set_offline() does not stop a service worker's requests.)"""

    def __init__(self, app):
        import threading
        self._threading = threading
        self.app = app
        self.port = 0
        self._srv = None

    def up(self):
        from werkzeug.serving import make_server
        import time as _t
        for attempt in range(60):                    # the port can take a moment to be released
            try:
                self._srv = make_server("127.0.0.1", self.port, self.app, threaded=True)
                break
            except OSError:
                if attempt == 59:
                    raise
                _t.sleep(0.25)
        self.port = self._srv.server_port
        self._threading.Thread(target=self._srv.serve_forever, daemon=True).start()
        return self

    def down(self):
        if self._srv:
            self._srv.shutdown()
            self._srv.server_close()
            self._srv = None

    @property
    def base(self):
        return f"http://127.0.0.1:{self.port}"


def wait_until(page, js_expression, timeout=30.0, poll=0.25):
    """Poll a JS expression (which may return a Promise) until it is truthy.
    page.wait_for_function() does NOT wait for a returned Promise to resolve -
    a pending Promise counts as truthy - so anything asynchronous (reading
    IndexedDB, say) has to be polled with page.evaluate(), which does."""
    import time
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = page.evaluate(js_expression)
        if last:
            return last
        time.sleep(poll)
    raise AssertionError(f"timed out waiting for: {js_expression} (last value: {last!r})")
