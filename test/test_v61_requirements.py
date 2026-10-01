from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]

def test_v61_core_requirements_are_present():
    app = (ROOT / "app.py").read_text()
    db = (ROOT / "db.py").read_text()
    login = (ROOT / "templates/student_login.html").read_text()
    admin_school = (ROOT / "templates/admin_school.html").read_text()
    result = (ROOT / "templates/result.html").read_text()
    assert "complete_enhancements_v61" in db
    assert "/dashboard/search" in app
    assert "first_login_required" in app and "class_login_code" in app
    assert "show_overall_position" in app and "show_subject_position" in app
    assert "show_subject_position" in result
    assert "Student Signup" not in (ROOT / "templates/login.html").read_text()
    assert "Username / Admission No. / Register No." in login
    assert "Result Sheet Template" in admin_school

def test_v61_python_syntax():
    for name in ("app.py", "db.py", "profile_core.py", "profile_routes.py", "pdf_utils.py"):
        ast.parse((ROOT / name).read_text())
