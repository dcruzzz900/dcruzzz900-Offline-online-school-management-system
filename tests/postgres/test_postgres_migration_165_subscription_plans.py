from postgres_migration_165_subscription_plans import (
    MIGRATION_NAME, MIGRATION_STATEMENTS, MIGRATION_VERSION, _EXPECTED_COLUMNS, migration,
)
from postgres_migration_registry import POSTGRES_MIGRATIONS


def test_migration_identity_and_registry():
    item = migration()
    assert item.version == 165
    assert item.name == MIGRATION_NAME == "create_subscription_plans"
    assert MIGRATION_VERSION == 165
    assert POSTGRES_MIGRATIONS[-23].version == 165
    assert [m.version for m in POSTGRES_MIGRATIONS] == list(range(100, 188))


def test_effective_sqlite_schema_is_preserved():
    expected = [
        "id", "code", "name", "price_ngn", "billing_days", "max_students",
        "max_teachers", "max_storage_mb", "features_json", "is_active",
        "created_at", "updated_at",
    ]
    assert list(_EXPECTED_COLUMNS) == expected
    sql = "\n".join(MIGRATION_STATEMENTS)
    for fragment in (
        "code TEXT NOT NULL UNIQUE", "price_ngn DOUBLE PRECISION NOT NULL DEFAULT 0",
        "billing_days BIGINT NOT NULL DEFAULT 365", "features_json TEXT NOT NULL DEFAULT '{}'",
        "is_active BIGINT NOT NULL DEFAULT 1", "idx_subscription_plans_active",
    ):
        assert fragment in sql
    assert "REFERENCES" not in sql.upper()


def test_migration_is_standalone_and_does_not_touch_sqlite_startup():
    item = migration()
    assert item.version == 165
    assert len(MIGRATION_STATEMENTS) == 2
