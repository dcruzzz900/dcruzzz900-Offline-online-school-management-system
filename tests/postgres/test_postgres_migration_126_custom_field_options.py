import pytest

from postgres_migration_126_custom_field_options import (
    MIGRATION_NAME, MIGRATION_SOURCE, MIGRATION_VERSION,
    apply_custom_field_options, migration,
)
from postgres_migration_registry import POSTGRES_MIGRATIONS


class Result:
    def __init__(self, rows): self.rows = rows
    def fetchall(self): return self.rows


class FakeConnection:
    def __init__(self, columns=None, indexes=None, fks=None, triggers=None):
        types = {
            "id": "bigint", "field_id": "bigint", "school_id": "bigint",
            "tenant_id": "text", "option_value": "text",
            "display_order": "bigint", "is_active": "bigint",
        }
        self.columns = columns if columns is not None else [
            {"column_name": n, "data_type": t, "is_nullable": "NO"}
            for n, t in types.items()
        ]
        self.indexes = indexes if indexes is not None else [
            {"indexname": "custom_field_options_pkey", "indexdef": "CREATE UNIQUE INDEX custom_field_options_pkey ON public.custom_field_options USING btree (id)"},
            {"indexname": "uq_custom_field_options_field_value", "indexdef": "CREATE UNIQUE INDEX uq_custom_field_options_field_value ON public.custom_field_options USING btree (field_id, option_value)"},
        ]
        self.fks = fks if fks is not None else []
        self.triggers = triggers if triggers is not None else []
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        if "information_schema.columns" in sql: return Result(self.columns)
        if "information_schema.table_constraints" in sql and "FOREIGN KEY" in sql: return Result(self.fks)
        if "FROM pg_indexes" in sql: return Result(self.indexes)
        if "information_schema.triggers" in sql: return Result(self.triggers)
        return Result([])


def test_custom_field_options_registered_in_order():
    assert MIGRATION_VERSION == 126
    assert MIGRATION_NAME == "create_custom_field_options"
    assert [item.version for item in POSTGRES_MIGRATIONS] == list(range(100, 188))
    assert next(item for item in POSTGRES_MIGRATIONS if item.version == 126).name == MIGRATION_NAME
    assert migration().version == 126


def test_ddl_preserves_columns_defaults_and_composite_uniqueness():
    sql = MIGRATION_SOURCE.lower()
    for fragment in (
        "field_id bigint not null", "school_id bigint not null", "tenant_id text not null",
        "option_value text not null", "display_order bigint not null default 0",
        "is_active bigint not null default 1",
        "unique (field_id, option_value)",
    ):
        assert fragment in sql


def test_apply_validates_and_executes_migration():
    conn = FakeConnection()
    apply_custom_field_options(conn)
    assert any("CREATE TABLE IF NOT EXISTS custom_field_options" in sql for sql, _ in conn.calls)


def test_apply_rejects_missing_column():
    columns = [r for r in FakeConnection().columns if r["column_name"] != "tenant_id"]
    with pytest.raises(RuntimeError, match="missing columns"):
        apply_custom_field_options(FakeConnection(columns=columns))


def test_apply_rejects_incompatible_column_type():
    columns = [dict(r) for r in FakeConnection().columns]
    next(r for r in columns if r["column_name"] == "field_id")["data_type"] = "integer"
    with pytest.raises(RuntimeError, match="incompatible columns"):
        apply_custom_field_options(FakeConnection(columns=columns))


def test_apply_rejects_unexpected_foreign_key():
    with pytest.raises(RuntimeError, match="unexpected foreign keys"):
        apply_custom_field_options(FakeConnection(fks=[{"constraint_name": "unexpected_fk"}]))


def test_apply_rejects_missing_or_incompatible_unique_index():
    indexes = [r for r in FakeConnection().indexes if r["indexname"] != "uq_custom_field_options_field_value"]
    with pytest.raises(RuntimeError, match="indexes"):
        apply_custom_field_options(FakeConnection(indexes=indexes))


def test_apply_rejects_unexpected_trigger():
    with pytest.raises(RuntimeError, match="unexpected triggers"):
        apply_custom_field_options(FakeConnection(triggers=[{"trigger_name": "unexpected_trigger"}]))
