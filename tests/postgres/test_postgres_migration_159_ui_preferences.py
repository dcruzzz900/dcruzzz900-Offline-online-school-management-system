from postgres_migration_159_ui_preferences import (
    MIGRATION_NAME, MIGRATION_STATEMENTS, MIGRATION_VERSION, _EXPECTED_COLUMNS, migration,
)
from postgres_migration_registry import POSTGRES_MIGRATIONS


def test_migration_identity_and_registry():
    item = migration()
    assert item.version == 159
    assert item.name == "create_ui_preferences"
    assert MIGRATION_VERSION == 159
    assert POSTGRES_MIGRATIONS[-29].version == 159
    assert [m.version for m in POSTGRES_MIGRATIONS] == list(range(100, 188))


def test_effective_sqlite_schema_shape_is_preserved():
    assert list(_EXPECTED_COLUMNS) == ["kind", "actor_id", "school_id", "theme", "font_scale", "updated_at"]
    sql = MIGRATION_STATEMENTS[0]
    assert "PRIMARY KEY (kind, actor_id)" in sql
    assert "font_scale BIGINT NOT NULL DEFAULT 100" in sql
    assert "updated_at TEXT DEFAULT CURRENT_TIMESTAMP" in sql
    assert len(MIGRATION_STATEMENTS) == 1
    assert "FOREIGN KEY" not in sql.upper()
    assert "CREATE TRIGGER" not in sql.upper()
