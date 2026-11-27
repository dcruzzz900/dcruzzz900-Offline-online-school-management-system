from postgres_migration_148_subscription_history import (
    migration, MIGRATION_STATEMENTS, MIGRATION_VERSION, _EXPECTED_COLUMNS,
)


def test_migration_identity_and_objects():
    item = migration()
    assert item.version == 148
    assert item.name == "create_subscription_history"
    assert MIGRATION_VERSION == 148
    assert "CREATE TABLE IF NOT EXISTS subscription_history" in MIGRATION_STATEMENTS[0]
    assert "idx_subscription_history_school" in MIGRATION_STATEMENTS[1]
    assert len(MIGRATION_STATEMENTS) == 6


def test_source_schema_matches_sqlite_definition():
    assert len(_EXPECTED_COLUMNS) == 14
    sql = MIGRATION_STATEMENTS[0]
    for column in ("previous_status", "new_status", "previous_plan", "new_plan", "previous_ends_at", "new_ends_at", "actor_id", "actor_name"):
        assert column in sql
    assert "school_id BIGINT NOT NULL" in sql
    assert "tenant_id TEXT" in sql
    assert "created_at TEXT DEFAULT CURRENT_TIMESTAMP" in sql


def test_subscription_history_is_append_only():
    assert "BEFORE UPDATE" in MIGRATION_STATEMENTS[3]
    assert "BEFORE DELETE" in MIGRATION_STATEMENTS[5]
    assert all("app_reject_immutable_row" in MIGRATION_STATEMENTS[i] for i in (3, 5))
