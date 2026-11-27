from postgres_migration_151_result_workflow_permissions import (
    MIGRATION_NAME, MIGRATION_STATEMENTS, MIGRATION_VERSION, _EXPECTED_COLUMNS, migration,
)
from postgres_migration_registry import POSTGRES_MIGRATIONS


def test_migration_identity_and_registry():
    item = migration()
    assert item.version == 151
    assert item.name == "create_result_workflow_permissions"
    assert MIGRATION_VERSION == 151
    assert POSTGRES_MIGRATIONS[-37].version == 151
    assert [m.version for m in POSTGRES_MIGRATIONS] == list(range(100, 188))


def test_source_schema_matches_effective_sqlite_definition():
    assert len(_EXPECTED_COLUMNS) == 8
    sql = MIGRATION_STATEMENTS[0]
    for column in ("school_id", "tenant_id", "user_id", "permission", "granted", "changed_by", "changed_at"):
        assert column in sql
    assert "granted BIGINT NOT NULL DEFAULT 1" in sql
    assert "UNIQUE (user_id, permission)" in sql
    assert "FOREIGN KEY" not in sql
