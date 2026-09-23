"""Phase: login by username/email/phone, staff email/phone contact fields,
student parent_relationship field, and passport photo upload — tested with
real HTTP requests against real SQLite data, per this project's usual rigor.
"""
from helpers import fresh_app, login, csrf


def _student_id(m, admission_no="001"):
    import db
    c = db.get_db()
    sid = c.execute("SELECT id FROM students WHERE admission_no=?", (admission_no,)).fetchone()[0]
    c.close()
    return sid


def _teacher_id(m):
    import db
    c = db.get_db()
    tid = c.execute("SELECT id FROM users WHERE username='aokafor'").fetchone()[0]
    c.close()
    return tid


# ---------- login by email / phone ----------

def test_login_by_email_and_phone_after_admin_sets_them():
    m, _ = fresh_app()
    admin = m.app.test_client()
    assert login(admin, "admin", "admin123").status_code == 302
    tid = _teacher_id(m)

    r = admin.post(f"/admin/teachers/{tid}/contact",
                    data={"csrf_token": csrf(admin), "email": "aokafor@example.com", "phone": "08011112222"},
                    follow_redirects=True)
    assert b"Contact info updated" in r.data

    # Username still works.
    assert login(m.app.test_client(), "aokafor", "teacher123").status_code == 302
    # Email works (case-insensitive).
    assert login(m.app.test_client(), "AOKAFOR@EXAMPLE.COM", "teacher123").status_code == 302
    # Phone works.
    assert login(m.app.test_client(), "08011112222", "teacher123").status_code == 302
    # Wrong password with a valid identifier still fails.
    assert login(m.app.test_client(), "aokafor@example.com", "wrongpass").status_code != 302


def test_duplicate_email_or_phone_is_rejected():
    m, _ = fresh_app()
    admin = m.app.test_client()
    assert login(admin, "admin", "admin123").status_code == 302
    tid = _teacher_id(m)
    admin.post(f"/admin/teachers/{tid}/contact",
               data={"csrf_token": csrf(admin), "email": "aokafor@example.com", "phone": "08011112222"})

    # Adding a new teacher with the same email is rejected.
    r = admin.post("/admin/teachers",
                    data={"csrf_token": csrf(admin), "name": "New Teacher", "username": "newteach",
                          "email": "aokafor@example.com", "phone": "", "password": "abcdef", "position": ""},
                    follow_redirects=True)
    assert b"already in use" in r.data
    import db
    c = db.get_db()
    assert c.execute("SELECT 1 FROM users WHERE username='newteach'").fetchone() is None
    c.close()

    # Same phone, different case-folding of email — both rejected.
    r = admin.post("/admin/teachers",
                    data={"csrf_token": csrf(admin), "name": "New Teacher 2", "username": "newteach2",
                          "email": "", "phone": "08011112222", "password": "abcdef", "position": ""},
                    follow_redirects=True)
    assert b"already in use" in r.data


def test_self_registration_with_email_rejects_duplicate_and_allows_login():
    m, _ = fresh_app()
    school_id = 1
    import db
    c = db.get_db()
    code = c.execute("SELECT staff_signup_code FROM schools WHERE id=?", (school_id,)).fetchone()
    if not code or not code[0]:
        c.execute("UPDATE schools SET staff_signup_code='letmein' WHERE id=?", (school_id,))
        c.commit()
    c.close()

    anon = m.app.test_client()
    anon.get("/register")
    r = anon.post("/register", data={
        "csrf_token": csrf(anon), "school_id": str(school_id), "name": "Grace Okoro",
        "username": "gokoro", "email": "grace@example.com", "phone": "08099998888",
        "password": "secret1", "confirm_password": "secret1", "signup_code": "letmein",
        "position": "subject_teacher", "security_question": "What town were you born in?",
        "security_answer": "Lagos",
    }, follow_redirects=True)
    assert b"Your login has been created" in r.data or r.status_code == 200

    assert login(m.app.test_client(), "grace@example.com", "secret1").status_code == 302
    assert login(m.app.test_client(), "08099998888", "secret1").status_code == 302


def test_my_own_contact_info_via_settings():
    m, _ = fresh_app()
    teacher = m.app.test_client()
    assert login(teacher, "aokafor", "teacher123").status_code == 302
    r = teacher.post("/account/contact", data={"csrf_token": csrf(teacher), "email": "me@example.com", "phone": "07000000000"},
                      follow_redirects=True)
    assert b"Contact info updated" in r.data
    assert login(m.app.test_client(), "me@example.com", "teacher123").status_code == 302


# ---------- parent_relationship ----------

def test_parent_relationship_saved_on_admin_add_and_edit():
    m, _ = fresh_app()
    admin = m.app.test_client()
    assert login(admin, "admin", "admin123").status_code == 302
    import db
    c = db.get_db()
    class_id = c.execute("SELECT id FROM classes LIMIT 1").fetchone()[0]
    c.close()

    r = admin.post("/admin/students", data={
        "csrf_token": csrf(admin), "admission_no": "099", "first_name": "Tunde", "last_name": "Bakare",
        "gender": "M", "class_id": str(class_id), "parent_relationship": "Uncle",
    }, follow_redirects=True)
    assert r.status_code == 200

    c = db.get_db()
    row = c.execute("SELECT id, parent_relationship FROM students WHERE admission_no='099'").fetchone()
    c.close()
    assert row["parent_relationship"] == "Uncle"

    sid = row["id"]
    r = admin.get(f"/students/{sid}/profile")
    assert b"Uncle" in r.data


def test_form_teacher_roster_add_and_inline_edit_save_relationship():
    m, _ = fresh_app()
    teacher = m.app.test_client()
    assert login(teacher, "aokafor", "teacher123").status_code == 302
    import db
    c = db.get_db()
    class_id = c.execute("SELECT id FROM classes LIMIT 1").fetchone()[0]
    c.close()

    teacher.post(f"/my-class/{class_id}", data={
        "csrf_token": csrf(teacher), "admission_no": "077", "first_name": "Ada", "last_name": "Eze",
        "parent_relationship": "Mother",
    })
    import db
    c = db.get_db()
    row = c.execute("SELECT id, parent_relationship FROM students WHERE admission_no='077'").fetchone()
    c.close()
    assert row["parent_relationship"] == "Mother"

    sid = row["id"]
    teacher.post(f"/my-class/{class_id}/students/{sid}/edit", data={
        "csrf_token": csrf(teacher), "admission_no": "077", "first_name": "Ada", "last_name": "Eze",
        "parent_relationship": "Aunt",
    })
    c = db.get_db()
    updated = c.execute("SELECT parent_relationship FROM students WHERE id=?", (sid,)).fetchone()[0]
    c.close()
    assert updated == "Aunt"


# ---------- passport photo ----------

def test_photo_upload_view_and_remove_with_access_control():
    import io
    m, _ = fresh_app()
    admin = m.app.test_client()
    assert login(admin, "admin", "admin123").status_code == 302
    sid = _student_id(m)

    # A 1x1 PNG.
    png_bytes = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
                 b"\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")

    r = admin.post(f"/students/{sid}/photo/upload", data={
        "csrf_token": csrf(admin), "photo": (io.BytesIO(png_bytes), "passport.png"),
    }, content_type="multipart/form-data", follow_redirects=True)
    assert b"Passport photo updated" in r.data

    r = admin.get(f"/students/{sid}/photo")
    assert r.status_code == 200
    assert r.data == png_bytes

    # A teacher not assigned to this student's class cannot view or upload.
    import db
    c = db.get_db()
    c.execute("INSERT INTO users (school_id, name, username, password_hash, role) "
              "VALUES (1, 'Other Teacher', 'otherteach', ?, 'teacher')",
              (m.generate_password_hash("otherpass1"),))
    c.commit()
    c.close()
    other = m.app.test_client()
    assert login(other, "otherteach", "otherpass1").status_code == 302
    assert other.get(f"/students/{sid}/photo").status_code == 404
    other.post(f"/students/{sid}/photo/upload", data={
        "csrf_token": csrf(other), "photo": (io.BytesIO(b"not-the-real-photo"), "passport.png"),
    }, content_type="multipart/form-data", follow_redirects=True)
    # The unauthorized upload must not have replaced the real photo.
    r = admin.get(f"/students/{sid}/photo")
    assert r.data == png_bytes

    r = admin.post(f"/students/{sid}/photo/remove", data={"csrf_token": csrf(admin)}, follow_redirects=True)
    assert b"Passport photo removed" in r.data
    assert admin.get(f"/students/{sid}/photo").status_code == 404
