from postgres_migration_157_signups import (
    MIGRATION_NAME, MIGRATION_STATEMENTS, MIGRATION_VERSION, _EXPECTED_COLUMNS, migration,
)
from postgres_migration_registry import POSTGRES_MIGRATIONS


def test_migration_identity_and_registry():
    item = migration()
    assert item.version == 157
    assert item.name == "create_signups"
    assert MIGRATION_VERSION == 157
    assert POSTGRES_MIGRATIONS[-31].version == 157
    assert [m.version for m in POSTGRES_MIGRATIONS] == list(range(100, 188))


def test_effective_sqlite_schema_shape_and_dependencies_are_preserved():
    assert len(_EXPECTED_COLUMNS) == 13
    sql = MIGRATION_STATEMENTS[0]
    for column in ("id", "user_id", "signup_type", "signup_status", "submitted_at",
                   "verified_at", "approved_at", "rejected_at", "correction_requested_at",
                   "school_id", "tenant_id", "request_id", "notes"):
        assert column in sql
    assert "signup_status TEXT NOT NULL DEFAULT 'pending'" in sql
    assert "FOREIGN KEY (user_id) REFERENCES users(id)" in sql
    assert "FOREIGN KEY (school_id) REFERENCES schools(id)" in sql
    assert "idx_signups_school_status" in MIGRATION_STATEMENTS[1]
    assert "(school_id, signup_status)" in MIGRATION_STATEMENTS[1]
    assert "CREATE TRIGGER" not in " ".join(MIGRATION_STATEMENTS).upper()
