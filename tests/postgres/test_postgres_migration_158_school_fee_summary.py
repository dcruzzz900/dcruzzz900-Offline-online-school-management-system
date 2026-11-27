from postgres_migration_158_school_fee_summary import (
    MIGRATION_NAME, MIGRATION_STATEMENTS, MIGRATION_VERSION, _EXPECTED_COLUMNS, migration,
)
from postgres_migration_registry import POSTGRES_MIGRATIONS


def test_migration_identity_and_registry():
    item = migration()
    assert item.version == 158
    assert item.name == "create_school_fee_summary"
    assert MIGRATION_VERSION == 158
    assert POSTGRES_MIGRATIONS[-30].version == 158
    assert [m.version for m in POSTGRES_MIGRATIONS] == list(range(100, 188))


def test_effective_sqlite_schema_shape_is_preserved():
    assert len(_EXPECTED_COLUMNS) == 6
    sql = MIGRATION_STATEMENTS[0]
    for column in ("id", "school_id", "label", "expected_amount", "collected_amount", "updated_at"):
        assert column in sql
    assert "expected_amount DOUBLE PRECISION NOT NULL DEFAULT 0" in sql
    assert "collected_amount DOUBLE PRECISION NOT NULL DEFAULT 0" in sql
    assert "idx_school_fee_summary_school" in MIGRATION_STATEMENTS[1]
    assert "(school_id, id)" in MIGRATION_STATEMENTS[1]
    assert "CREATE TRIGGER" not in " ".join(MIGRATION_STATEMENTS).upper()
