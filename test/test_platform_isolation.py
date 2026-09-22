"""Only the Super Admin (platform admin) can manage schools. School admins,
sub-admins, teachers and logged-out visitors must not be able to suspend,
archive, delete, re-code or force-logout ANY school - including their own -
nor read the platform pages."""
from werkzeug.security import generate_password_hash
from helpers import fresh_app, login, csrf, make_school


def _school_state(b):
    import db
    c = db.get_db()
    row = c.execute("SELECT * FROM schools WHERE id=?", (b["school_id"],)).fetchone()
    users = c.execute("SELECT COUNT(*) FROM users WHERE school_id=?", (b["school_id"],)).fetchone()[0]
    pw = c.execute("SELECT password_hash FROM users WHERE id=?", (b["admin_id"],)).fetchone()[0]
    c.close()
    return (tuple(row), users, pw)


def _attack(client, b, my_school_id):
    hits = []
    for sid in (b["school_id"], my_school_id):
        for action in ("activate", "archive", "delete", "force_logout", "regenerate_code", "suspend", "unarchive"):
            r = client.post(f"/platform/schools/{sid}/{action}", data={"csrf_token": csrf(client)})
            if r.status_code == 200 and b"Super Admin" in r.data:
                hits.append(action)
    r = client.post(f"/platform/users/{b['admin_id']}/reset_password", data={"csrf_token": csrf(client), "new_password": "owned-123"})
    for path in ("/platform/dashboard", "/platform/schools", "/platform/users", "/platform/audit", "/platform/schools/export"):
        r = client.get(path)
        if r.status_code == 200 and (b"Platform" in r.data or b"School B" in r.data):
            hits.append(path)
    return hits


def test_school_level_users_and_visitors_cannot_manage_schools():
    m, _ = fresh_app()
    b = make_school(m)
    import db
    conn = db.get_db()
    conn.execute("UPDATE users SET role='sub_admin' WHERE username='aokafor'")
    conn.commit()
    my_school = conn.execute("SELECT school_id FROM users WHERE username='admin'").fetchone()[0]
    conn.close()
    before_b = _school_state(b)
    for who in (("admin", "admin123"), ("aokafor", "teacher123"), None):
        c = m.app.test_client()
        if who:
            assert login(c, *who).status_code == 302
        else:
            c.get("/login")
        hits = _attack(c, b, my_school)
        assert not hits, (who, hits)
    assert _school_state(b) == before_b
    conn = db.get_db()
    assert conn.execute("SELECT is_suspended, activation_status FROM schools WHERE id=?", (my_school,)).fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM schools").fetchone()[0] == 2
    conn.close()


def test_positive_control_platform_admin_can_suspend_a_school():
    m, _ = fresh_app()
    b = make_school(m)
    import db
    conn = db.get_db()
    conn.execute("INSERT INTO platform_admins (name, username, password_hash) VALUES ('Root','root',?)",
                 (generate_password_hash("root-pass-1"),))
    conn.commit()
    conn.close()
    c = m.app.test_client()
    c.get("/platform/login")
    r = c.post("/platform/login", data={"username": "root", "password": "root-pass-1", "csrf_token": csrf(c)})
    assert r.status_code == 302
    r = c.post(f"/platform/schools/{b['school_id']}/suspend", data={"csrf_token": csrf(c)}, follow_redirects=True)
    conn = db.get_db()
    assert conn.execute("SELECT is_suspended FROM schools WHERE id=?", (b["school_id"],)).fetchone()[0] == 1
    conn.close()
