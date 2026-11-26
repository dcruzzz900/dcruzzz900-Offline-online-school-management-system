import pytest

from postgres_migration_122_billing_report_downloads import (
    MIGRATION_NAME, MIGRATION_SOURCE, MIGRATION_VERSION,
    apply_billing_report_downloads, migration,
)
from postgres_migration_registry import POSTGRES_MIGRATIONS


class Result:
    def __init__(self, rows): self.rows = rows
    def fetchall(self): return self.rows
    def fetchone(self): return self.rows[0] if self.rows else None


class FakeConnection:
    def __init__(self, columns=None, indexes=None, triggers=None, fks=None):
        types = {"id": "bigint", "actor_type": "text", "actor_name": "text",
                 "report_name": "text", "format": "text", "start_date": "text",
                 "end_date": "text", "row_count": "bigint", "created_at": "text"}
        nullable = {"actor_name", "start_date", "end_date"}
        self.columns = columns if columns is not None else [
            {"column_name": n, "data_type": t, "is_nullable": "YES" if n in nullable else "NO"}
            for n, t in types.items()]
        self.indexes = indexes if indexes is not None else [
            {"indexname": "billing_report_downloads_pkey", "indexdef": "CREATE UNIQUE INDEX billing_report_downloads_pkey ON public.billing_report_downloads USING btree (id)"},
            {"indexname": "idx_billing_report_downloads_created", "indexdef": "CREATE INDEX idx_billing_report_downloads_created ON public.billing_report_downloads USING btree (created_at)"},
        ]
        self.triggers = triggers if triggers is not None else [
            {"trigger_name": "trg_billing_report_downloads_no_update"},
            {"trigger_name": "trg_billing_report_downloads_no_delete"},
        ]
        self.fks = fks if fks is not None else []
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        if "information_schema.columns" in sql: return Result(self.columns)
        if "information_schema.table_constraints" in sql: return Result(self.fks)
        if "FROM pg_indexes" in sql: return Result(self.indexes)
        if "information_schema.triggers" in sql: return Result(self.triggers)
        return Result([])


def test_billing_report_downloads_registered_in_order():
    assert MIGRATION_VERSION == 122
    assert MIGRATION_NAME == "create_billing_report_downloads"
    assert [item.version for item in POSTGRES_MIGRATIONS] == list(range(100, 143))
    assert next(item for item in POSTGRES_MIGRATIONS if item.version == 122).name == MIGRATION_NAME
    assert migration().version == 122


def test_ddl_preserves_source_columns_index_and_immutability():
    sql = MIGRATION_SOURCE.lower()
    for fragment in (
        "actor_type text not null", "actor_name text", "report_name text not null",
        "format text not null", "row_count bigint not null default 0",
        "created_at text not null default current_timestamp",
        "idx_billing_report_downloads_created on billing_report_downloads (created_at)",
        "before update", "before delete", "report download records are immutable",
    ):
        assert fragment in sql


def test_apply_validates_and_executes_migration():
    conn = FakeConnection()
    apply_billing_report_downloads(conn)
    assert any("CREATE TABLE IF NOT EXISTS billing_report_downloads" in sql for sql, _ in conn.calls)


def test_apply_rejects_missing_column():
    columns = [r for r in FakeConnection().columns if r["column_name"] != "report_name"]
    with pytest.raises(RuntimeError, match="missing columns"):
        apply_billing_report_downloads(FakeConnection(columns=columns))


def test_apply_rejects_incompatible_column_type():
    columns = [dict(r) for r in FakeConnection().columns]
    next(r for r in columns if r["column_name"] == "row_count")["data_type"] = "integer"
    with pytest.raises(RuntimeError, match="incompatible columns"):
        apply_billing_report_downloads(FakeConnection(columns=columns))


def test_apply_rejects_unexpected_foreign_key():
    with pytest.raises(RuntimeError, match="unexpected foreign keys"):
        apply_billing_report_downloads(FakeConnection(fks=[{"column_name": "actor_name"}]))


def test_apply_rejects_missing_lookup_index():
    indexes = [r for r in FakeConnection().indexes if r["indexname"] != "idx_billing_report_downloads_created"]
    with pytest.raises(RuntimeError, match="indexes"):
        apply_billing_report_downloads(FakeConnection(indexes=indexes))


def test_apply_rejects_missing_immutable_trigger():
    with pytest.raises(RuntimeError, match="immutable triggers"):
        apply_billing_report_downloads(FakeConnection(triggers=[{"trigger_name": "trg_billing_report_downloads_no_update"}]))
