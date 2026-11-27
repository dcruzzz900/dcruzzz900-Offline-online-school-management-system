from postgres_migration_156_signup_codes import (
    MIGRATION_NAME, MIGRATION_STATEMENTS, MIGRATION_VERSION, _EXPECTED_COLUMNS, migration,
)
from postgres_migration_registry import POSTGRES_MIGRATIONS


def test_migration_identity_and_registry():
    item = migration()
    assert item.version == 156
    assert item.name == "create_signup_codes"
    assert MIGRATION_VERSION == 156
    assert POSTGRES_MIGRATIONS[-32].version == 156
    assert [m.version for m in POSTGRES_MIGRATIONS] == list(range(100, 188))


def test_effective_sqlite_schema_shape_is_preserved():
    assert len(_EXPECTED_COLUMNS) == 18
    sql = MIGRATION_STATEMENTS[0]
    for column in ("id", "code", "code_type", "school_id", "tenant_id", "class_id", "student_id",
                   "created_by", "created_at", "expires_at", "max_usage", "usage_count", "status",
                   "last_used_at", "revoked_at", "revoked_by", "session_id", "class_arm"):
        assert column in sql
    assert "uq_signup_codes_code UNIQUE" in sql
    assert "code_type IN ('staff', 'student', 'parent_link')" in sql
    assert "status IN ('active', 'expired', 'exhausted', 'revoked', 'suspended')" in sql
    assert "FOREIGN KEY (school_id) REFERENCES schools(id)" in sql
    assert "idx_signup_codes_school_type" in MIGRATION_STATEMENTS[1]
    assert "(school_id, code_type, status)" in MIGRATION_STATEMENTS[1]
    assert "CREATE TRIGGER" not in " ".join(MIGRATION_STATEMENTS).upper()
