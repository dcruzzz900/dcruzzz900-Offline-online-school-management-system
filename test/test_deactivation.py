"""Deactivating a staff account (ported from the queue-based build) must cut
off the person everywhere: new logins, live sessions, and every offline device
they enrolled - including one that is offline at the time and only finds out
when it reconnects."""
from helpers import fresh_app, login, csrf, enroll, device_headers, new_device, push, change, bootstrap


def _teacher_id(m):
    import db
    c = db.get_db()
    tid = c.execute("SELECT id FROM users WHERE username='aokafor'").fetchone()[0]
    c.close()
    return tid


def test_deactivated_teacher_loses_login_session_and_devices_then_can_be_reactivated():
    m, _ = fresh_app()
    tid = _teacher_id(m)
    teacher = m.app.test_client()
    assert login(teacher, "aokafor", "teacher123").status_code == 302
    dev, cred = new_device(m, "aokafor", "teacher123", "phone")
    assert bootstrap(dev, cred)["entities"]["students"] is not None

    admin = m.app.test_client()
    assert login(admin, "admin", "admin123").status_code == 302
    r = admin.post(f"/admin/teachers/{tid}/toggle_active", data={"csrf_token": csrf(admin)}, follow_redirects=True)
    assert b"deactivated" in r.data.lower()

    assert teacher.get("/dashboard", follow_redirects=False).status_code == 302        # live session ended
    assert teacher.get("/dashboard", follow_redirects=True).request.path == "/login"
    assert login(m.app.test_client(), "aokafor", "teacher123").status_code != 302      # can't log in
    r = dev.get("/api/sync/bootstrap", headers=device_headers(cred))
    assert r.status_code == 401                                                        # offline device is cut off
    v = dev.post("/api/offline/verify", json={"device_id": cred["device_id"], "device_secret": cred["device_secret"]}).get_json()
    assert v["status"] == "revoked"

    admin.post(f"/admin/teachers/{tid}/toggle_active", data={"csrf_token": csrf(admin)})
    assert login(m.app.test_client(), "aokafor", "teacher123").status_code == 302      # back in
    # ...but the old device stays revoked until the teacher logs in on it again and renews
    assert dev.get("/api/sync/bootstrap", headers=device_headers(cred)).status_code == 401
