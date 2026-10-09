from pathlib import Path
import ast,re

ROOT=Path(__file__).resolve().parents[1]
APP=(ROOT/'app.py').read_text()
BASE=(ROOT/'templates/base.html').read_text()

def test_approved_role_catalog_present():
    for role in ["School Admin","Sub-Admin","Form Teacher","Subject Teacher","Discipline Master","Guidance/Counselor","Librarian","Labour Master","Non-Teaching Staff"]:
        assert f'"{role}"' in APP

def test_production_navigation_is_merged_and_renamed():
    assert 'Reports &amp; Analytics' in BASE
    assert '>Reports</span>' not in BASE
    assert '>Analytics</span>' not in BASE
    assert 'Staff Attendance' in BASE

def test_stable_pages_have_routes():
    assert '@app.route("/dashboard")' in APP
    assert '@app.route("/school-dashboard")' in APP
    assert '@app.route("/school-setup")' in APP
    assert '@app.route("/result/<int:student_id>")' in APP

def test_subject_teacher_is_blocked_from_full_results():
    assert 'def can_enter_scores' in APP and 'def require_class_result_access' in APP
    assert 'You don\'t have access to view results for this class.' in APP

def test_staff_attendance_self_routes_exist():
    assert '@app.route("/staff-attendance/check-in", methods=["POST"])' in APP
    assert '@app.route("/staff-attendance/check-out", methods=["POST"])' in APP
    assert 'staff-attendance/check-in' in (ROOT/'templates/staff_attendance.html').read_text()

def test_no_visible_version_labels():
    for p in (ROOT/'templates').glob('*.html'):
        text=p.read_text()
        assert not re.search(r'\bV(?:38|39|40|41|42|43|44|45|46|47|48|49|50|51|52)\b', text, re.I), p.name
