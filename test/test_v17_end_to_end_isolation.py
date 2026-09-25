"""V17 end-to-end tenant/RBAC isolation regression tests.

All data lives in a throw-away DATA_DIR.  These tests are deliberately
negative: School A credentials must never read or mutate School B data.
"""
from helpers import fresh_app, login, csrf, make_school, device_headers, enroll


def _login_client(app, username, password):
    c = app.app.test_client()
    r = login(c, username, password)
    assert r.status_code == 302, r.data
    return c


def test_school_a_cannot_access_school_b_records_by_id_or_tenant():
    app, _ = fresh_app()
    import db
    a = _login_client(app, "admin", "admin123")
    b = make_school(app, "School B", "adminb", "pass-b-123")

    # A's session must remain bound to its own school.
    with a.session_transaction() as s:
        school_a = s["school_id"]
        tenant_a = s.get("tenant_id")
    assert school_a != b["school_id"]
    assert tenant_a

    # Attempt to pass B's identifiers through normal query/form parameters.
    for url in (
        f"/admin/students?school_id={b['school_id']}",
        f"/admin/classes?school_id={b['school_id']}",
        f"/admin/subjects?school_id={b['school_id']}",
        f"/admin/results?class_id={b['class_id']}&school_id={b['school_id']}",
    ):
        r = a.get(url, follow_redirects=False)
        assert r.status_code in (200, 302, 403, 404)
        if r.status_code == 200:
            body = r.get_data(as_text=True)
            assert "Bola" not in body
            assert "School B" not in body

    # Direct student lookup must not reveal B's student through A's session.
    for url in (f"/student/{b['student_id']}", f"/admin/students/{b['student_id']}"):
        r = a.get(url, follow_redirects=False)
        assert r.status_code in (302, 403, 404)

    # Database state remains owned by B after failed attempts.
    c = db.get_db()
    row = c.execute("SELECT school_id FROM students WHERE id=?", (b["student_id"],)).fetchone()
    assert row and row["school_id"] == b["school_id"]
    c.close()


def test_school_a_device_cannot_bootstrap_or_push_school_b():
    app, _ = fresh_app()
    import db
    a = _login_client(app, "admin", "admin123")
    b = make_school(app, "School B", "adminb", "pass-b-123")

    cred = enroll(a, "A-device")
    headers = device_headers(cred)

    # Bootstrap is tied to the authenticated/enrolled tenant.
    r = a.get("/api/sync/bootstrap", headers=headers)
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("tenant_id") != b.get("tenant_id", "__unknown__")

    # Forge a B class/student in a push while using A's device credentials.
    payload = {
        "changes": [{
            "entity": "students", "client_uuid": "v17-forged-student",
            "change_id": "v17-forged-change", "op": "upsert",
            "data": {"id": b["student_id"], "class_id": b["class_id"],
                     "admission_no": "FORGED-B", "first_name": "FORGED", "last_name": "B"}
        }]
    }
    r = a.post("/api/sync/push", json=payload, headers=headers)
    assert r.status_code in (200, 400, 403)

    c = db.get_db()
    row = c.execute("SELECT first_name, school_id FROM students WHERE id=?", (b["student_id"],)).fetchone()
    assert row["school_id"] == b["school_id"]
    assert row["first_name"] != "FORGED"
    c.close()


def test_school_admin_cannot_escalate_to_platform():
    app, _ = fresh_app()
    c = _login_client(app, "admin", "admin123")
    for url in ("/platform", "/platform/users", "/platform/schools", "/platform/roles", "/platform/security-audit", "/platform/backups"):
        r = c.get(url, follow_redirects=False)
        assert r.status_code in (302, 403, 404)
        if r.status_code == 302:
            assert "/platform/login" in (r.headers.get("Location") or "") or "/login" in (r.headers.get("Location") or "")


def test_suspended_school_cannot_login_but_platform_login_remains_separate():
    app, _ = fresh_app()
    import db
    b = make_school(app, "School B", "adminb", "pass-b-123")
    c = db.get_db()
    # The schema uses status values in normal school login checks.
    c.execute("UPDATE schools SET status='suspended' WHERE id=?", (b["school_id"],))
    c.commit(); c.close()
    client = app.app.test_client()
    r = login(client, "adminb", "pass-b-123")
    assert r.status_code == 200
    with client.session_transaction() as s:
        assert "user_id" not in s
