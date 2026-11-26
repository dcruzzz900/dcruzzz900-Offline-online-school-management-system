import pytest

from postgres_migration_124_change_audit import (
    MIGRATION_NAME, MIGRATION_SOURCE, MIGRATION_VERSION,
    apply_change_audit, migration,
)
from postgres_migration_registry import POSTGRES_MIGRATIONS


class Result:
    def __init__(self, rows): self.rows = rows
    def fetchall(self): return self.rows


class FakeConnection:
    def __init__(self, columns=None, indexes=None, triggers=None, fks=None):
        types = {
            "id": "bigint", "school_id": "integer", "entity": "text",
            "client_uuid": "text", "change_id": "text", "op": "text",
            "outcome": "text", "device_id": "text", "user_id": "integer",
            "client_ts": "text", "server_ts": "text", "server_id": "integer",
            "result_updated_at": "text", "old_data": "text", "new_data": "text", "note": "text",
        }
        nullable = {"client_uuid", "change_id", "op", "device_id", "user_id", "client_ts", "server_ts", "server_id", "result_updated_at", "old_data", "new_data", "note"}
        self.columns = columns if columns is not None else [
            {"column_name": n, "data_type": t, "is_nullable": "YES" if n in nullable else "NO"}
            for n, t in types.items()
        ]
        self.indexes = indexes if indexes is not None else [
            {"indexname": "change_audit_pkey", "indexdef": "CREATE UNIQUE INDEX change_audit_pkey ON public.change_audit USING btree (id)"},
            {"indexname": "idx_change_audit_change_id", "indexdef": "CREATE UNIQUE INDEX idx_change_audit_change_id ON public.change_audit USING btree (school_id, change_id) WHERE ((change_id IS NOT NULL) AND (outcome = ANY (ARRAY['applied'::text, 'merged'::text, 'latest_wins'::text])))"},
            {"indexname": "idx_change_audit_record", "indexdef": "CREATE INDEX idx_change_audit_record ON public.change_audit USING btree (school_id, entity, client_uuid)"},
            {"indexname": "idx_change_audit_school", "indexdef": "CREATE INDEX idx_change_audit_school ON public.change_audit USING btree (school_id, id)"},
        ]
        self.fks = fks if fks is not None else [{"column_name": "school_id", "foreign_table_name": "schools", "foreign_column_name": "id"}]
        self.triggers = triggers if triggers is not None else []
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        if "information_schema.columns" in sql: return Result(self.columns)
        if "information_schema.table_constraints" in sql: return Result(self.fks)
        if "FROM pg_indexes" in sql: return Result(self.indexes)
        if "information_schema.triggers" in sql: return Result(self.triggers)
        return Result([])


def test_change_audit_registered_in_order():
    assert MIGRATION_VERSION == 124
    assert MIGRATION_NAME == "create_change_audit"
    assert [item.version for item in POSTGRES_MIGRATIONS] == list(range(100, 143))
    assert next(item for item in POSTGRES_MIGRATIONS if item.version == 124).name == MIGRATION_NAME
    assert migration().version == 124


def test_ddl_preserves_source_columns_and_partial_unique_index():
    sql = MIGRATION_SOURCE.lower()
    for fragment in (
        "school_id integer not null references schools(id)",
        "server_ts text default current_timestamp",
        "idx_change_audit_change_id", "where change_id is not null",
        "outcome in ('applied','merged','latest_wins')",
        "idx_change_audit_record on change_audit (school_id, entity, client_uuid)",
        "idx_change_audit_school on change_audit (school_id, id)",
    ):
        assert fragment in sql


def test_apply_validates_and_executes_migration():
    conn = FakeConnection()
    apply_change_audit(conn)
    assert any("CREATE TABLE IF NOT EXISTS change_audit" in sql for sql, _ in conn.calls)


def test_apply_rejects_missing_column():
    columns = [r for r in FakeConnection().columns if r["column_name"] != "outcome"]
    with pytest.raises(RuntimeError, match="missing columns"):
        apply_change_audit(FakeConnection(columns=columns))


def test_apply_rejects_incompatible_column_type():
    columns = [dict(r) for r in FakeConnection().columns]
    next(r for r in columns if r["column_name"] == "school_id")["data_type"] = "bigint"
    with pytest.raises(RuntimeError, match="incompatible columns"):
        apply_change_audit(FakeConnection(columns=columns))


def test_apply_rejects_wrong_foreign_key():
    with pytest.raises(RuntimeError, match="foreign keys"):
        apply_change_audit(FakeConnection(fks=[{"column_name": "school_id", "foreign_table_name": "users", "foreign_column_name": "id"}]))


def test_apply_rejects_missing_or_incompatible_indexes():
    indexes = [r for r in FakeConnection().indexes if r["indexname"] != "idx_change_audit_change_id"]
    with pytest.raises(RuntimeError, match="indexes"):
        apply_change_audit(FakeConnection(indexes=indexes))


def test_apply_rejects_unexpected_trigger():
    with pytest.raises(RuntimeError, match="unexpected triggers"):
        apply_change_audit(FakeConnection(triggers=[{"trigger_name": "unexpected_trigger"}]))
