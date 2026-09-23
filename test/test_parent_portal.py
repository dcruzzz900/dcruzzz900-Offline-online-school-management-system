"""Phase: Parent Profile as a real entity — login-capable parent accounts
linked to one or more students, with a read-only parent portal.
"""
from helpers import fresh_app, login, parent_login, csrf


def _first_student_admission_no():
    import db
    c = db.get_db()
    adm = c.execute("SELECT admission_no FROM students ORDER BY id LIMIT 1").fetchone()[0]
    c.close()
    return adm


def _add_demo_parent(admin, admission_no, relationship="Mother"):
    return admin.post("/admin/parents", data={
        "csrf_token": csrf(admin), "name": "Mrs Chidinma Okafor", "phone": "08055556666",
        "email": "chidinma@example.com", "address": "12 Broad St", "password": "parentpw1",
        "admission_no": admission_no, "relationship": relationship,
    }, follow_redirects=True)


def test_admin_can_add_parent_linked_to_a_child_and_parent_can_log_in():
    m, _ = fresh_app()
    admin = m.app.test_client()
    assert login(admin, "admin", "admin123").status_code == 302
    adm = _first_student_admission_no()

    r = _add_demo_parent(admin, adm)
    assert b"added" in r.data

    import db
    c = db.get_db()
    parent = c.execute("SELECT * FROM parents WHERE phone='08055556666'").fetchone()
    link = c.execute("SELECT relationship FROM parent_students WHERE parent_id=?", (parent["id"],)).fetchone()
    c.close()
    assert parent is not None
    assert link["relationship"] == "Mother"

    assert parent_login(m.app.test_client(), "chidinma@example.com", "parentpw1").status_code == 302
    assert parent_login(m.app.test_client(), "08055556666", "parentpw1").status_code == 302
    assert parent_login(m.app.test_client(), "chidinma@example.com", "wrongpass").status_code != 302


def test_duplicate_phone_or_email_rejected_across_parent_accounts():
    m, _ = fresh_app()
    admin = m.app.test_client()
    assert login(admin, "admin", "admin123").status_code == 302
    adm = _first_student_admission_no()
    _add_demo_parent(admin, adm)

    r = admin.post("/admin/parents", data={
        "csrf_token": csrf(admin), "name": "Mr Someone", "phone": "08055556666", "email": "",
        "password": "abcdefgh",
    }, follow_redirects=True)
    assert b"already registered" in r.data
    import db
    c = db.get_db()
    assert c.execute("SELECT COUNT(*) FROM parents").fetchone()[0] == 1
    c.close()


def test_parent_only_sees_their_own_linked_children():
    m, _ = fresh_app()
    admin = m.app.test_client()
    assert login(admin, "admin", "admin123").status_code == 302
    import db
    c = db.get_db()
    rows = c.execute("SELECT admission_no, id FROM students ORDER BY id").fetchall()
    my_adm, my_sid = rows[0]["admission_no"], rows[0]["id"]
    other_sid = rows[1]["id"]
    c.close()

    _add_demo_parent(admin, my_adm)
    parent = m.app.test_client()
    assert parent_login(parent, "chidinma@example.com", "parentpw1").status_code == 302

    r = parent.get(f"/parent/children/{my_sid}")
    assert r.status_code == 200

    r = parent.get(f"/parent/children/{other_sid}", follow_redirects=True)
    assert b"don&#39;t have access" in r.data or b"don't have access" in r.data

    # A staff-only page must not be reachable with a parent session.
    r = parent.get("/admin/students", follow_redirects=False)
    assert r.status_code == 302


def test_deactivated_parent_cannot_log_in_and_reactivation_restores_access():
    m, _ = fresh_app()
    admin = m.app.test_client()
    assert login(admin, "admin", "admin123").status_code == 302
    adm = _first_student_admission_no()
    _add_demo_parent(admin, adm)

    import db
    c = db.get_db()
    pid = c.execute("SELECT id FROM parents WHERE phone='08055556666'").fetchone()[0]
    c.close()

    admin.post(f"/admin/parents/{pid}/toggle_active", data={"csrf_token": csrf(admin)}, follow_redirects=True)
    assert parent_login(m.app.test_client(), "chidinma@example.com", "parentpw1").status_code != 302

    admin.post(f"/admin/parents/{pid}/toggle_active", data={"csrf_token": csrf(admin)}, follow_redirects=True)
    assert parent_login(m.app.test_client(), "chidinma@example.com", "parentpw1").status_code == 302


def test_admin_can_link_and_unlink_a_second_child():
    m, _ = fresh_app()
    admin = m.app.test_client()
    assert login(admin, "admin", "admin123").status_code == 302
    import db
    c = db.get_db()
    rows = c.execute("SELECT admission_no, id FROM students ORDER BY id").fetchall()
    adm1, adm2, sid2 = rows[0]["admission_no"], rows[1]["admission_no"], rows[1]["id"]
    c.close()
    _add_demo_parent(admin, adm1)

    c = db.get_db()
    pid = c.execute("SELECT id FROM parents WHERE phone='08055556666'").fetchone()[0]
    c.close()

    r = admin.post(f"/admin/parents/{pid}/link", data={
        "csrf_token": csrf(admin), "admission_no": adm2, "relationship": "Guardian",
    }, follow_redirects=True)
    assert r.status_code == 200
    c = db.get_db()
    assert c.execute("SELECT COUNT(*) FROM parent_students WHERE parent_id=?", (pid,)).fetchone()[0] == 2
    c.close()

    admin.post(f"/admin/parents/{pid}/unlink/{sid2}", data={"csrf_token": csrf(admin)}, follow_redirects=True)
    c = db.get_db()
    assert c.execute("SELECT COUNT(*) FROM parent_students WHERE parent_id=?", (pid,)).fetchone()[0] == 1
    c.close()


def test_admin_reset_parent_password_and_delete():
    m, _ = fresh_app()
    admin = m.app.test_client()
    assert login(admin, "admin", "admin123").status_code == 302
    adm = _first_student_admission_no()
    _add_demo_parent(admin, adm)
    import db
    c = db.get_db()
    pid = c.execute("SELECT id FROM parents WHERE phone='08055556666'").fetchone()[0]
    c.close()

    r = admin.post(f"/admin/parents/{pid}/reset_password", data={"csrf_token": csrf(admin)}, follow_redirects=True)
    assert b"New temporary password" in r.data
    # Old password no longer works.
    assert parent_login(m.app.test_client(), "chidinma@example.com", "parentpw1").status_code != 302

    admin.post(f"/admin/parents/{pid}/delete", data={"csrf_token": csrf(admin)}, follow_redirects=True)
    c = db.get_db()
    assert c.execute("SELECT 1 FROM parents WHERE id=?", (pid,)).fetchone() is None
    assert c.execute("SELECT 1 FROM parent_students WHERE parent_id=?", (pid,)).fetchone() is None
    c.close()


def test_cross_school_isolation_for_parent_accounts():
    """A parent created under School A must never be linkable to a School B student."""
    m, _ = fresh_app()
    from helpers import make_school
    make_school(m, name="School B", admin_username="adminb", password="pass-b-123")
    admin = m.app.test_client()
    assert login(admin, "admin", "admin123").status_code == 302
    adm = _first_student_admission_no()
    admin.post("/admin/parents", data={
        "csrf_token": csrf(admin), "name": "Cross School Parent", "phone": "07011112222",
        "email": "cross@example.com", "password": "abcdefgh",
        "admission_no": adm,
    }, follow_redirects=True)

    admin_b = m.app.test_client()
    assert login(admin_b, "adminb", "pass-b-123").status_code == 302
    import db
    c = db.get_db()
    pid = c.execute("SELECT id FROM parents WHERE phone='07011112222'").fetchone()[0]
    c.close()
    # School B's admin must not be able to manage School A's parent account.
    r = admin_b.post(f"/admin/parents/{pid}/toggle_active", data={"csrf_token": csrf(admin_b)}, follow_redirects=True)
    assert b"Parent not found" in r.data
