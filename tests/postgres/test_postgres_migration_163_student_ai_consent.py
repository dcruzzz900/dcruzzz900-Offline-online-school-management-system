from postgres_migration_163_student_ai_consent import (
    MIGRATION_NAME, MIGRATION_STATEMENTS, MIGRATION_VERSION, _EXPECTED_COLUMNS, migration,
)
from postgres_migration_registry import POSTGRES_MIGRATIONS


def test_migration_identity_and_registry():
    item = migration()
    assert item.version == 163
    assert item.name == MIGRATION_NAME == "create_student_ai_consent"
    assert MIGRATION_VERSION == 163
    assert POSTGRES_MIGRATIONS[-25].version == 163
    assert [m.version for m in POSTGRES_MIGRATIONS] == list(range(100, 188))


def test_effective_sqlite_schema_and_tenant_behaviour_are_preserved():
    expected = [
        "student_id", "school_id", "status", "granted_by_type", "granted_by_id",
        "policy_version", "granted_at", "withdrawn_at", "notes", "tenant_id",
        "granted_by_name", "relationship", "recorded_by", "recorded_at",
    ]
    assert list(_EXPECTED_COLUMNS) == expected
    sql = "\n".join(MIGRATION_STATEMENTS)
    for fragment in (
        "student_id BIGINT PRIMARY KEY", "school_id BIGINT NOT NULL",
        "status TEXT NOT NULL DEFAULT 'pending'", "'pending', 'granted', 'withdrawn'",
        "idx_ai_consent_school_status", "granted_by_name TEXT", "relationship TEXT",
        "recorded_by BIGINT", "recorded_at TEXT", "tenant_id TEXT",
        "BEFORE INSERT ON student_ai_consent", "FROM schools WHERE id = NEW.school_id",
    ):
        assert fragment in sql
    assert "REFERENCES" not in sql.upper()


def test_migration_is_standalone_and_does_not_touch_sqlite_startup():
    item = migration()
    assert item.version == 163
    assert len(MIGRATION_STATEMENTS) == 5
