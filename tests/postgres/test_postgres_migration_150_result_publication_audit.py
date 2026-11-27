from postgres_migration_150_result_publication_audit import (
    MIGRATION_NAME, MIGRATION_STATEMENTS, MIGRATION_VERSION, _EXPECTED_COLUMNS, migration,
)
from postgres_migration_registry import POSTGRES_MIGRATIONS


def test_migration_identity_and_registry():
    item = migration()
    assert item.version == 150
    assert item.name == "create_result_publication_audit"
    assert MIGRATION_VERSION == 150
    assert POSTGRES_MIGRATIONS[-38].version == 150
    assert [m.version for m in POSTGRES_MIGRATIONS] == list(range(100, 188))


def test_source_schema_matches_sqlite_definition():
    assert len(_EXPECTED_COLUMNS) == 15
    sql = MIGRATION_STATEMENTS[0]
    for column in ("school_id", "tenant_id", "publication_id", "class_id", "term_id", "action",
                   "previous_status", "new_status", "actor_id", "actor_name", "actor_role", "reason",
                   "event_date", "server_timestamp"):
        assert column in sql
    assert "server_timestamp TEXT NOT NULL" in sql
    assert "clock_timestamp() AT TIME ZONE 'UTC'" in sql


def test_scope_index_and_append_only_triggers_are_preserved():
    assert "idx_pub_audit_scope" in MIGRATION_STATEMENTS[1]
    assert "(school_id, class_id, term_id, id)" in MIGRATION_STATEMENTS[1]
    assert any("BEFORE DELETE" in sql for sql in MIGRATION_STATEMENTS)
    assert any("BEFORE UPDATE" in sql for sql in MIGRATION_STATEMENTS)
