from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def test_v52_security_schema_and_public_labels():
    db=(ROOT/"db.py").read_text(); app=(ROOT/"app.py").read_text(); login=(ROOT/"templates/login.html").read_text(); student=(ROOT/"templates/register_student.html").read_text(); parent=(ROOT/"templates/register_parent.html").read_text()
    assert "migration_052_auth_signup_audit_spec" in db
    for table in ("signups","activation_attempts","status_history","security_events"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in db
    assert "STAFF_SIGNUP_COMPLETED" in app
    assert "STUDENT_ACCOUNT_CREATED" in app
    assert "PARENT_ACCOUNT_CREATED" in app
    assert "New School Signup" in login and "Staff Signup" in login and "Student Signup" in login and "Parent Signup" in login
    assert "Super Admin" not in login
    assert "Admission Number / Register Number *" in student
    assert "Parent Linking Code" not in parent

def test_v52_student_signup_never_inserts_new_student_record():
    app=(ROOT/"app.py").read_text(); start=app.index('def register_student():'); end=app.index('@app.route("/register/parent"',start); block=app[start:end]
    assert 'INSERT INTO students' not in block
    assert 'UPDATE students SET username=' in block
    assert 'already been registered' in block
