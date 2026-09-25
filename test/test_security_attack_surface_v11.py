"""V11 security regression tests.

These tests exercise tenant-boundary, role-escalation and offline-credential
attack paths without touching a real production database.
"""
import re
from helpers import fresh_app, login, csrf, make_school, enroll, device_headers, change


def _second_school():
    app, _ = fresh_app()
    b = make_school(app)
    return app, b


def test_tenant_ids_are_not_client_authoritative_on_normal_login():
    app, b = _second_school()
    c = app.app.test_client()
    assert login(c, "admin", "admin123").status_code == 302
    # Supplying another school's identifiers must not change the authenticated tenant.
    r = c.get(f"/students/{b['student_id']}/profile?tenant_id={b['school_id']}&school_id={b['school_id']}")
    assert r.status_code in (302, 403, 404)
    body = r.get_data().decode("utf-8", "ignore")
    assert not re.search(r"School B|Bola|B001", body)


def test_school_admin_cannot_escalate_to_platform_or_modify_other_school():
    app, b = _second_school()
    c = app.app.test_client()
    assert login(c, "admin", "admin123").status_code == 302
    for path in ("/platform/dashboard", "/platform/schools", "/platform/users", "/platform/security-audit"):
        r = c.get(path)
        assert r.status_code in (302, 403, 404)
    before = app.db.get_db().execute("SELECT is_suspended FROM schools WHERE id=?", (b["school_id"],)).fetchone()[0]
    r = c.post(f"/platform/schools/{b['school_id']}/suspend", data={"csrf_token": csrf(c)})
    assert r.status_code in (302, 403, 404)
    after = app.db.get_db().execute("SELECT is_suspended FROM schools WHERE id=?", (b["school_id"],)).fetchone()[0]
    assert before == after == 0


def test_offline_device_secret_cannot_be_rebound_to_another_tenant():
    app, b = _second_school()
    c = app.app.test_client()
    assert login(c, "admin", "admin123").status_code == 302
    cred = enroll(c, "v11-device")
    forged = dict(cred)
    forged["tenant_id"] = b["school_id"]
    r = app.app.test_client().get("/api/sync/bootstrap", headers=device_headers(forged))
    assert r.status_code in (401, 403)


def test_offline_push_rejects_foreign_class_and_student():
    app, b = _second_school()
    c = app.app.test_client()
    assert login(c, "admin", "admin123").status_code == 302
    cred = enroll(c, "v11-push")
    foreign = change("students", {"id": b["student_id"], "class_id": b["class_id"], "first_name": "HACK"})
    r = c.post("/api/sync/push", json={"changes": [foreign]}, headers=device_headers(cred))
    assert r.status_code in (200, 400, 401, 403)
    row = app.db.get_db().execute("SELECT first_name FROM students WHERE id=?", (b["student_id"],)).fetchone()
    assert row[0] == "Bola"


def test_suspended_school_cannot_use_normal_login():
    app, b = _second_school()
    db = app.db.get_db()
    db.execute("UPDATE schools SET is_suspended=1 WHERE id=?", (b["school_id"],))
    db.commit()
    c = app.app.test_client()
    assert login(c, b["admin"][0], b["admin"][1]).status_code in (200, 302, 403)
    with c.session_transaction() as s:
        assert s.get("user_id") is None


def test_role_assignment_cannot_grant_super_admin():
    app, _ = _second_school()
    c = app.app.test_client()
    assert login(c, "admin", "admin123").status_code == 302
    r = c.post("/admin/roles", data={
        "name": "Escalation Attempt", "username": "x", "role": "Super Admin",
        "school_level": "All", "csrf_token": csrf(c)
    })
    assert r.status_code in (200, 302, 400, 403)
    rows = app.db.get_db().execute("SELECT role FROM role_assignments WHERE role LIKE '%Super%' ").fetchall()
    assert not rows
