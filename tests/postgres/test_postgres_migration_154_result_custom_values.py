from postgres_migration_154_result_custom_values import (
    MIGRATION_NAME, MIGRATION_STATEMENTS, MIGRATION_VERSION, _EXPECTED_COLUMNS, migration,
)
from postgres_migration_registry import POSTGRES_MIGRATIONS


def test_migration_identity_and_registry():
    item = migration()
    assert item.version == 154
    assert item.name == "create_result_custom_values"
    assert MIGRATION_VERSION == 154
    assert POSTGRES_MIGRATIONS[-34].version == 154
    assert [m.version for m in POSTGRES_MIGRATIONS] == list(range(100, 188))


def test_effective_sqlite_schema_shape_and_uniqueness_are_preserved():
    assert len(_EXPECTED_COLUMNS) == 7
    sql = MIGRATION_STATEMENTS[0]
    for column in ("school_id", "student_id", "term_id", "field_id", "value", "updated_at"):
        assert column in sql
    assert "updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP" in sql
    assert "UNIQUE (student_id, term_id, field_id)" in sql
    assert "FOREIGN KEY" not in sql
    assert "CREATE TRIGGER" not in sql.upper()
