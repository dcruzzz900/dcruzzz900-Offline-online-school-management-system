from postgres_migration_164_student_ai_consent_events import (
    MIGRATION_NAME, MIGRATION_STATEMENTS, MIGRATION_VERSION, _EXPECTED_COLUMNS, migration,
)
from postgres_migration_registry import POSTGRES_MIGRATIONS


def test_migration_identity_and_registry():
    item = migration()
    assert item.version == 164
    assert item.name == MIGRATION_NAME == "create_student_ai_consent_events"
    assert MIGRATION_VERSION == 164
    assert POSTGRES_MIGRATIONS[-24].version == 164
    assert [m.version for m in POSTGRES_MIGRATIONS] == list(range(100, 188))


def test_effective_sqlite_schema_and_history_behaviour_are_preserved():
    expected = [
        "id", "school_id", "tenant_id", "student_id", "previous_status", "new_status",
        "consenting_name", "relationship", "policy_version", "notes",
        "recorded_by_type", "recorded_by_id", "recorded_by_name", "server_timestamp",
    ]
    assert list(_EXPECTED_COLUMNS) == expected
    sql = "\n".join(MIGRATION_STATEMENTS)
    for fragment in (
        "school_id BIGINT NOT NULL", "student_id BIGINT NOT NULL",
        "new_status TEXT NOT NULL", "idx_ai_consent_events",
        "recorded_by_type TEXT", "recorded_by_id BIGINT", "recorded_by_name TEXT",
        "server_timestamp TEXT NOT NULL", "History is append-only",
        "BEFORE UPDATE ON student_ai_consent_events", "BEFORE DELETE ON student_ai_consent_events",
    ):
        assert fragment in sql
    assert "REFERENCES" not in sql.upper()


def test_migration_is_standalone_and_does_not_touch_sqlite_startup():
    item = migration()
    assert item.version == 164
    assert len(MIGRATION_STATEMENTS) == 7
