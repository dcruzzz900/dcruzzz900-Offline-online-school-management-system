from postgres_migration_155_result_display_settings import (
    MIGRATION_NAME, MIGRATION_STATEMENTS, MIGRATION_VERSION, _EXPECTED_COLUMNS, migration,
)
from postgres_migration_registry import POSTGRES_MIGRATIONS


def test_migration_identity_and_registry():
    item = migration()
    assert item.version == 155
    assert item.name == "create_result_display_settings"
    assert MIGRATION_VERSION == 155
    assert POSTGRES_MIGRATIONS[-33].version == 155
    assert [m.version for m in POSTGRES_MIGRATIONS] == list(range(100, 188))


def test_effective_sqlite_schema_shape_and_defaults_are_preserved():
    assert len(_EXPECTED_COLUMNS) == 57
    sql = MIGRATION_STATEMENTS[0]
    for column in ("school_id", "tenant_id", "template", "show_next_term_resumes", "text_align", "page_orientation", "font_scale", "paper_size", "custom_width_mm", "custom_height_mm"):
        assert column in sql
    assert "school_id BIGINT PRIMARY KEY" in sql
    assert "template TEXT NOT NULL DEFAULT 'professional_classic'" in sql
    assert "updated_at TEXT DEFAULT CURRENT_TIMESTAMP" in sql
    assert "FOREIGN KEY" not in sql
    assert "CREATE TRIGGER" not in sql.upper()
