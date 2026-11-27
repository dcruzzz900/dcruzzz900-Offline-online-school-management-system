from postgres_migration_162_school_ai_settings import (
    MIGRATION_NAME, MIGRATION_STATEMENTS, MIGRATION_VERSION, _EXPECTED_COLUMNS, migration,
)
from postgres_migration_registry import POSTGRES_MIGRATIONS


def test_migration_identity_and_registry():
    item = migration()
    assert item.version == 162
    assert item.name == "create_school_ai_settings"
    assert MIGRATION_VERSION == 162
    assert POSTGRES_MIGRATIONS[-26].version == 162
    assert [m.version for m in POSTGRES_MIGRATIONS] == list(range(100, 188))


def test_effective_sqlite_schema_shape_is_preserved():
    expected = [
        "school_id", "enabled", "process_student_data", "result_analysis",
        "teacher_comments", "principal_comments", "performance_alerts",
        "ai_tutor", "learning_materials", "result_assistant", "retention_days",
        "privacy_notice_version", "updated_by", "updated_at", "tenant_id",
    ]
    assert list(_EXPECTED_COLUMNS) == expected
    sql = MIGRATION_STATEMENTS[0]
    for fragment in (
        "school_id BIGINT PRIMARY KEY", "enabled BIGINT NOT NULL DEFAULT 0",
        "process_student_data BIGINT NOT NULL DEFAULT 0",
        "result_analysis BIGINT NOT NULL DEFAULT 1",
        "teacher_comments BIGINT NOT NULL DEFAULT 1",
        "principal_comments BIGINT NOT NULL DEFAULT 1",
        "performance_alerts BIGINT NOT NULL DEFAULT 1",
        "ai_tutor BIGINT NOT NULL DEFAULT 1",
        "learning_materials BIGINT NOT NULL DEFAULT 1",
        "result_assistant BIGINT NOT NULL DEFAULT 0",
        "retention_days BIGINT NOT NULL DEFAULT 365",
        "privacy_notice_version TEXT NOT NULL DEFAULT '1.0'",
        "updated_by BIGINT", "updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP",
        "tenant_id TEXT",
    ):
        assert fragment in sql
    assert len(MIGRATION_STATEMENTS) == 1
    assert "FOREIGN KEY" not in sql.upper()
    assert "CREATE TRIGGER" not in sql.upper()
