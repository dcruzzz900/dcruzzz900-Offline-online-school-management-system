from postgres_migration_153_result_custom_fields import (
    MIGRATION_NAME, MIGRATION_STATEMENTS, MIGRATION_VERSION, _EXPECTED_COLUMNS, migration,
)
from postgres_migration_registry import POSTGRES_MIGRATIONS


def test_migration_identity_and_registry():
    item = migration()
    assert item.version == 153
    assert item.name == "create_result_custom_fields"
    assert MIGRATION_VERSION == 153
    assert POSTGRES_MIGRATIONS[-35].version == 153
    assert [m.version for m in POSTGRES_MIGRATIONS] == list(range(100, 188))


def test_effective_sqlite_schema_shape_and_index_are_preserved():
    assert len(_EXPECTED_COLUMNS) == 10
    sql = MIGRATION_STATEMENTS[0]
    for column in ("school_id", "tenant_id", "label", "field_type", "options", "sort_order", "is_active", "show_on_sheet", "created_at"):
        assert column in sql
    assert "field_type TEXT NOT NULL DEFAULT 'text'" in sql
    assert "sort_order BIGINT NOT NULL DEFAULT 0" in sql
    assert "show_on_sheet BIGINT NOT NULL DEFAULT 1" in sql
    assert "ux_result_custom_fields_label" in MIGRATION_STATEMENTS[1]
    assert "LOWER(label)" in MIGRATION_STATEMENTS[1]
    assert "school_id" in MIGRATION_STATEMENTS[1]
