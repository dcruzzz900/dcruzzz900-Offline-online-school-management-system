from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def test_v52_security_schema_and_public_labels():
    db=(ROOT/"db.py").read_text(); app=(ROOT/"app.py").read_text(); login=(ROOT/"templates/login.html").read_text(); parent=(ROOT/"templates/register_parent.html").read_text()
    assert "migration_052_auth_signup_audit_spec" in db
    for table in ("signups","activation_attempts","status_history","security_events"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in db
    assert "STAFF_SIGNUP_COMPLETED" in app
    assert "student_first_login_completed" in app
    assert "PARENT_ACCOUNT_CREATED" in app
    assert "New School Signup" in login and "Staff Signup" in login and "Parent Signup" in login and "Student Signup" not in login
    assert "Super Admin" not in login
    assert "Username / Admission No. / Register No." in (ROOT/"templates/student_login.html").read_text()
    assert "Parent Linking Code" not in parent

def test_v52_student_signup_is_removed():
    app=(ROOT/"app.py").read_text()
    login=(ROOT/"templates/login.html").read_text()
    assert "/student/login" in app
    assert "register_student" not in app
    assert "Student Signup" not in login
