"""Static regression contracts for the integrated AI v0.2.0 layer."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app.py").read_text()
DB = (ROOT / "db.py").read_text()


def route_block(route, next_route):
    start = APP.index(route)
    end = APP.index(next_route, start)
    return APP[start:end]


def test_ai_v2_migration_is_named_and_additive():
    assert '("ai_v2_cbt_module", migration_076_ai_v2_cbt_module)' in DB
    assert 'CREATE TABLE IF NOT EXISTS ai_cbt_sets' in DB
    assert 'ensure_column(conn, "school_ai_settings", col, typ)' in DB


def test_new_staff_modules_use_existing_school_authentication():
    for name in ("ai_teacher_assistant", "ai_cbt_generator", "ai_attendance_intelligence"):
        assert f"def {name}():" in APP
    assert '@login_required("admin", "sub_admin", "teacher")\ndef ai_teacher_assistant' in APP
    assert '@login_required("admin", "sub_admin", "teacher")\ndef ai_cbt_generator' in APP
    assert '@login_required("admin", "sub_admin", "teacher")\ndef ai_attendance_intelligence' in APP
    assert '@login_required("admin", "sub_admin")\ndef ai_management_assistant' in APP


def test_cbt_records_are_tenant_and_school_scoped():
    block = route_block('@app.route("/ai/cbt-generator"', '@app.route("/admin/theme"')
    assert 'current_tenant_id()' in block
    assert 'WHERE id=? AND school_id=? AND tenant_id=?' in block
    assert 'teacher' in block and 'get_accessible_class_ids' in block
    assert 'status="draft"' in block or '"draft"' in block


def test_cbt_drafts_do_not_publish_or_insert_live_exam_questions():
    block = route_block('@app.route("/ai/cbt/<int:set_id>/review"', '@app.route("/ai/attendance-intelligence")')
    assert "does not publish" in block
    assert "UPDATE ai_cbt_sets" in block
    assert "INSERT INTO" not in block


def test_attendance_and_management_are_read_only_aggregates():
    assert 'def ai_attendance_intelligence()' in APP
    assert 'COUNT(ar.id) records' in APP
    assert 'def ai_management_assistant()' in APP
    assert 'INSERT INTO' not in route_block('@app.route("/ai/management-assistant")', '@app.route("/admin/theme"')


def test_multi_provider_router_has_three_provider_adapters():
    provider = (ROOT / "ai" / "provider.py").read_text()
    for name in ("openai", "gemini", "anthropic"):
        assert name in provider.lower()
    assert "AI_API_URL" in provider and "OPENAI_API_KEY" in provider


def test_all_eight_ai_modules_are_linked_from_command_center():
    html = (ROOT / "templates" / "ai_command_center.html").read_text()
    for endpoint in ("ai_result_analysis", "ai_comments", "ai_learning_materials", "ai_teacher_assistant",
                     "ai_cbt_generator", "ai_attendance_intelligence", "ai_management_assistant"):
        assert endpoint in html
    assert "student_ai_tutor" in html


def test_new_migration_runs_after_all_v104_schema_steps():
    assert 'STEPS.append(("ai_v2_cbt_module", migration_076_ai_v2_cbt_module))' in DB
    assert DB.index('STEPS.append(("ai_v2_cbt_module"') > DB.index('STEPS.append(("announcements_v104"')


def test_student_tutor_validates_the_existing_student_tenant_session():
    block = route_block('@app.route("/student/ai-tutor"', '@app.route("/admin/theme"')
    assert 'session.get("tenant_id")' in block
    assert 'FROM students WHERE id=? AND school_id=? AND tenant_id=?' in block
