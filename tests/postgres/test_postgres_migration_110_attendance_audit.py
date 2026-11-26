from postgres_migration_110_attendance_audit import (
    MIGRATION_NAME, MIGRATION_SOURCE, MIGRATION_VERSION, migration,
)
from postgres_migration_registry import POSTGRES_MIGRATIONS


def test_attendance_audit_migration_is_registered_in_order():
    assert MIGRATION_VERSION == 110
    assert MIGRATION_NAME == "create_attendance_audit"
    assert [item.version for item in POSTGRES_MIGRATIONS] == list(range(100, 143))
    assert next(item for item in POSTGRES_MIGRATIONS if item.version == MIGRATION_VERSION).name == MIGRATION_NAME


def test_attendance_audit_ddl_preserves_source_contract():
    sql = MIGRATION_SOURCE.lower()
    for column in (
        "school_id", "tenant_id", "subject_type", "subject_id", "class_id", "class_arm",
        "term_id", "attendance_date", "status", "previous_status", "action", "recorded_by",
        "recorder_name", "recorder_role", "correction_reason", "corrected_by", "corrected_at",
        "server_timestamp",
    ):
        assert column in sql
    assert "subject_type in ('student', 'staff')" in sql
    assert "action in ('record', 'correct', 'check_in', 'check_out')" in sql
    assert "idx_attendance_audit_scope on attendance_audit (school_id, subject_type, attendance_date)" in sql
    assert "trg_attendance_audit_no_update" in sql
    assert "trg_attendance_audit_no_delete" in sql
    assert "history is append-only" in sql
    assert "references " not in sql


def test_migration_metadata():
    item = migration()
    assert item.version == 110
    assert item.name == MIGRATION_NAME
    assert item.source == MIGRATION_SOURCE
    assert callable(item.apply)
