from postgres_migration_149_result_publication import (
    MIGRATION_NAME, MIGRATION_STATEMENTS, MIGRATION_VERSION, _EXPECTED_COLUMNS, migration,
)
from postgres_migration_registry import POSTGRES_MIGRATIONS


def test_migration_identity_and_registry():
    item = migration()
    assert item.version == 149
    assert item.name == "create_result_publication"
    assert MIGRATION_VERSION == 149
    assert POSTGRES_MIGRATIONS[-39].version == 149
    assert [m.version for m in POSTGRES_MIGRATIONS] == list(range(100, 188))


def test_source_schema_matches_sqlite_definition():
    assert len(_EXPECTED_COLUMNS) == 17
    sql = MIGRATION_STATEMENTS[0]
    for column in ("school_id", "tenant_id", "class_id", "term_id", "submitted_by", "reviewed_by",
                   "approved_by", "published_by", "last_reason", "updated_by", "updated_at"):
        assert column in sql
    assert "DEFAULT 'draft'" in sql
    assert "UNIQUE (school_id, class_id, term_id)" in sql


def test_publication_status_domain_is_preserved():
    sql = MIGRATION_STATEMENTS[0]
    for status in ("draft", "submitted", "under_review", "returned", "approved", "published", "reopened"):
        assert f"'{status}'" in sql
