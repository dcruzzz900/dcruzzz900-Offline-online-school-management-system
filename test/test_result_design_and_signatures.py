"""Phase: result design customization (theme color, school-name alignment,
preview) and digital signatures for teachers/principals.
"""
import io
from helpers import fresh_app, login, csrf

PNG_BYTES = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
             b"\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")


def _school_name(m):
    import db
    c = db.get_db()
    name = c.execute("SELECT name FROM schools WHERE id=1").fetchone()[0]
    c.close()
    return name


def test_admin_can_save_result_design_settings():
    m, _ = fresh_app()
    admin = m.app.test_client()
    assert login(admin, "admin", "admin123").status_code == 302
    r = admin.post("/admin/school", data={
        "csrf_token": csrf(admin), "school_name": _school_name(m), "logo_align": "center",
        "school_name_align": "right", "result_theme_color": "#8a2b2b",
        "web_font": "system", "pdf_font": "Helvetica",
    }, follow_redirects=True)
    assert r.status_code == 200

    import db
    c = db.get_db()
    row = c.execute("SELECT school_name_align, result_theme_color FROM schools WHERE id=1").fetchone()
    c.close()
    assert row["school_name_align"] == "right"
    assert row["result_theme_color"] == "#8a2b2b"


def test_invalid_theme_color_falls_back_to_default():
    m, _ = fresh_app()
    admin = m.app.test_client()
    assert login(admin, "admin", "admin123").status_code == 302
    admin.post("/admin/school", data={
        "csrf_token": csrf(admin), "school_name": _school_name(m), "logo_align": "center",
        "school_name_align": "center", "result_theme_color": "not-a-color; </style><script>1</script>",
        "web_font": "system", "pdf_font": "Helvetica",
    }, follow_redirects=True)
    import db
    c = db.get_db()
    color = c.execute("SELECT result_theme_color FROM schools WHERE id=1").fetchone()[0]
    c.close()
    assert color == "#1f3a5f"


def test_preview_result_design_shows_submitted_unsaved_values_and_does_not_save():
    m, _ = fresh_app()
    admin = m.app.test_client()
    assert login(admin, "admin", "admin123").status_code == 302
    r = admin.post("/admin/school/preview-result-design", data={
        "csrf_token": csrf(admin), "school_name": _school_name(m), "logo_align": "center",
        "school_name_align": "left", "result_theme_color": "#123456",
    }, follow_redirects=True)
    assert r.status_code == 200
    assert b"#123456" in r.data
    assert b"text-align:left" in r.data
    assert b"Preview only" in r.data

    import db
    c = db.get_db()
    saved = c.execute("SELECT result_theme_color, school_name_align FROM schools WHERE id=1").fetchone()
    c.close()
    assert saved["result_theme_color"] != "#123456"
    assert saved["school_name_align"] != "left"


def test_teacher_signature_upload_toggle_and_access_control():
    m, _ = fresh_app()
    teacher = m.app.test_client()
    assert login(teacher, "aokafor", "teacher123").status_code == 302

    r = teacher.post("/account/signature/upload", data={
        "csrf_token": csrf(teacher), "signature": (io.BytesIO(PNG_BYTES), "sig.png"),
    }, content_type="multipart/form-data", follow_redirects=True)
    assert b"Signature uploaded" in r.data

    import db
    c = db.get_db()
    tid = c.execute("SELECT id FROM users WHERE username='aokafor'").fetchone()[0]
    c.close()

    # Not enabled yet — serving route must 404.
    assert teacher.get(f"/signature/{tid}").status_code == 404

    r = teacher.post("/account/signature/toggle", data={"csrf_token": csrf(teacher)}, follow_redirects=True)
    assert b"enabled" in r.data
    r = teacher.get(f"/signature/{tid}")
    assert r.status_code == 200 and r.data == PNG_BYTES

    # Toggle off again — serving must 404 even though the file is still there.
    teacher.post("/account/signature/toggle", data={"csrf_token": csrf(teacher)}, follow_redirects=True)
    assert teacher.get(f"/signature/{tid}").status_code == 404

    # A different school's staff must never see this signature.
    from helpers import make_school
    make_school(m, name="School B", admin_username="adminb", password="pass-b-123")
    admin_b = m.app.test_client()
    assert login(admin_b, "adminb", "pass-b-123").status_code == 302
    assert admin_b.get(f"/signature/{tid}").status_code == 404


def test_signature_removed_after_remove_and_after_reupload_replaces_file():
    m, _ = fresh_app()
    teacher = m.app.test_client()
    assert login(teacher, "aokafor", "teacher123").status_code == 302
    teacher.post("/account/signature/upload", data={
        "csrf_token": csrf(teacher), "signature": (io.BytesIO(PNG_BYTES), "sig.png"),
    }, content_type="multipart/form-data", follow_redirects=True)
    teacher.post("/account/signature/toggle", data={"csrf_token": csrf(teacher)}, follow_redirects=True)

    import db
    c = db.get_db()
    tid = c.execute("SELECT id FROM users WHERE username='aokafor'").fetchone()[0]
    c.close()
    assert teacher.get(f"/signature/{tid}").status_code == 200

    r = teacher.post("/account/signature/remove", data={"csrf_token": csrf(teacher)}, follow_redirects=True)
    assert b"Signature removed" in r.data
    assert teacher.get(f"/signature/{tid}").status_code == 404

    c = db.get_db()
    row = c.execute("SELECT signature_filename, use_digital_signature FROM users WHERE id=?", (tid,)).fetchone()
    c.close()
    assert row["signature_filename"] is None
    assert row["use_digital_signature"] == 0


def test_form_teacher_signature_appears_on_result_page_and_pdf_generates():
    m, _ = fresh_app()
    teacher = m.app.test_client()
    assert login(teacher, "aokafor", "teacher123").status_code == 302
    teacher.post("/account/signature/upload", data={
        "csrf_token": csrf(teacher), "signature": (io.BytesIO(PNG_BYTES), "sig.png"),
    }, content_type="multipart/form-data", follow_redirects=True)
    teacher.post("/account/signature/toggle", data={"csrf_token": csrf(teacher)}, follow_redirects=True)

    import db
    c = db.get_db()
    tid = c.execute("SELECT id FROM users WHERE username='aokafor'").fetchone()[0]
    class_id = c.execute("SELECT id FROM classes LIMIT 1").fetchone()[0]
    c.close()

    admin = m.app.test_client()
    assert login(admin, "admin", "admin123").status_code == 302
    admin.post(f"/admin/classes/{class_id}/set_teacher", data={
        "csrf_token": csrf(admin), "teacher_id": str(tid),
    }, follow_redirects=True)

    import db
    c = db.get_db()
    sid = c.execute("SELECT id FROM students WHERE class_id=? LIMIT 1", (class_id,)).fetchone()[0]
    term_id = c.execute("SELECT id FROM terms LIMIT 1").fetchone()[0]
    c.close()

    r = admin.get(f"/result/{sid}?term_id={term_id}")
    assert r.status_code == 200
    assert f"/signature/{tid}".encode() in r.data

    r = admin.get(f"/result/{sid}/pdf?term_id={term_id}")
    assert r.status_code == 200
    assert r.content_type == "application/pdf"


def test_result_without_any_signature_still_renders_blank_line_as_before():
    """No form teacher assigned, no principal signature enabled anywhere —
    the page and PDF must still render fine with the old blank-line style."""
    m, _ = fresh_app()
    admin = m.app.test_client()
    assert login(admin, "admin", "admin123").status_code == 302
    import db
    c = db.get_db()
    sid = c.execute("SELECT id FROM students LIMIT 1").fetchone()[0]
    term_id = c.execute("SELECT id FROM terms LIMIT 1").fetchone()[0]
    c.close()
    r = admin.get(f"/result/{sid}?term_id={term_id}")
    assert r.status_code == 200
    assert b"Teacher's Signature: __________________" in r.data or b"__________________" in r.data
    r = admin.get(f"/result/{sid}/pdf?term_id={term_id}")
    assert r.status_code == 200
