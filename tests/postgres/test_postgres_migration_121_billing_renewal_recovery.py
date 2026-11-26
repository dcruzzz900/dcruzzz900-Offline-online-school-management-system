import pytest

from postgres_migration_121_billing_renewal_recovery import (
    MIGRATION_NAME, MIGRATION_SOURCE, MIGRATION_VERSION,
    apply_billing_renewal_recovery, migration,
)
from postgres_migration_registry import POSTGRES_MIGRATIONS


class Result:
    def __init__(self, rows): self.rows = rows
    def fetchall(self): return self.rows
    def fetchone(self): return self.rows[0] if self.rows else None


class FakeConnection:
    def __init__(self, dependency_types=None, columns=None, fks=None, indexes=None, triggers=None):
        self.types = dependency_types or {"billing_invoices": "bigint", "schools": "integer"}
        types = {"id": "bigint", "invoice_id": "bigint", "school_id": "integer", "attempt_no": "bigint",
                 "next_attempt_at": "text", "status": "text", "last_message": "text", "created_at": "text", "updated_at": "text"}
        nullable = {"next_attempt_at", "last_message"}
        self.columns = columns if columns is not None else [
            {"column_name": n, "data_type": t, "is_nullable": "YES" if n in nullable else "NO"} for n, t in types.items()]
        self.fks = fks if fks is not None else [
            {"column_name": "invoice_id", "foreign_table_name": "billing_invoices", "foreign_column_name": "id"},
            {"column_name": "school_id", "foreign_table_name": "schools", "foreign_column_name": "id"},
        ]
        self.indexes = indexes if indexes is not None else [
            {"indexname": "billing_renewal_recovery_pkey", "indexdef": "CREATE UNIQUE INDEX billing_renewal_recovery_pkey ON public.billing_renewal_recovery USING btree (id)"},
            {"indexname": "uq_billing_renewal_recovery_invoice_attempt", "indexdef": "CREATE UNIQUE INDEX uq_billing_renewal_recovery_invoice_attempt ON public.billing_renewal_recovery USING btree (invoice_id, attempt_no)"},
            {"indexname": "idx_billing_recovery_status", "indexdef": "CREATE INDEX idx_billing_recovery_status ON public.billing_renewal_recovery USING btree (status, next_attempt_at)"},
        ]
        self.triggers = triggers if triggers is not None else []
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        if "table_name = ? AND column_name = ?" in sql:
            value = self.types.get(params[0])
            return Result([{"data_type": value}] if value else [])
        if "information_schema.columns" in sql: return Result(self.columns)
        if "information_schema.table_constraints" in sql: return Result(self.fks)
        if "FROM pg_indexes" in sql: return Result(self.indexes)
        if "information_schema.triggers" in sql: return Result(self.triggers)
        return Result([])


def test_billing_renewal_recovery_registered_in_order():
    assert MIGRATION_VERSION == 121
    assert MIGRATION_NAME == "create_billing_renewal_recovery"
    assert [item.version for item in POSTGRES_MIGRATIONS] == list(range(100, 143))
    assert next(item for item in POSTGRES_MIGRATIONS if item.version == 121).name == MIGRATION_NAME
    assert migration().version == 121


def test_ddl_preserves_source_columns_constraints_and_index():
    sql = MIGRATION_SOURCE.lower()
    for fragment in (
        "invoice_id bigint not null", "school_id integer not null", "attempt_no bigint not null default 1",
        "status text not null default 'queued'", "created_at text not null default current_timestamp",
        "updated_at text not null default current_timestamp", "unique (invoice_id, attempt_no)",
        "references billing_invoices(id)", "references schools(id)",
        "idx_billing_recovery_status on billing_renewal_recovery (status, next_attempt_at)",
    ):
        assert fragment in sql


def test_apply_validates_and_executes_migration():
    conn = FakeConnection()
    apply_billing_renewal_recovery(conn)
    assert any("CREATE TABLE IF NOT EXISTS billing_renewal_recovery" in sql for sql, _ in conn.calls)


@pytest.mark.parametrize("dependency,wrong_type", [("billing_invoices", "integer"), ("schools", "bigint")])
def test_apply_rejects_incompatible_dependency_key_type(dependency, wrong_type):
    types = {"billing_invoices": "bigint", "schools": "integer"}
    types[dependency] = wrong_type
    with pytest.raises(RuntimeError, match="requires"):
        apply_billing_renewal_recovery(FakeConnection(dependency_types=types))


def test_apply_rejects_missing_foreign_key():
    with pytest.raises(RuntimeError, match="foreign keys"):
        apply_billing_renewal_recovery(FakeConnection(fks=[]))


def test_apply_rejects_missing_scheduling_index():
    indexes = [r for r in FakeConnection().indexes if r["indexname"] != "idx_billing_recovery_status"]
    with pytest.raises(RuntimeError, match="indexes"):
        apply_billing_renewal_recovery(FakeConnection(indexes=indexes))


def test_apply_rejects_missing_unique_key_index():
    indexes = [r for r in FakeConnection().indexes if r["indexname"] != "uq_billing_renewal_recovery_invoice_attempt"]
    with pytest.raises(RuntimeError, match="indexes"):
        apply_billing_renewal_recovery(FakeConnection(indexes=indexes))


def test_apply_rejects_unexpected_trigger():
    with pytest.raises(RuntimeError, match="unexpected triggers"):
        apply_billing_renewal_recovery(FakeConnection(triggers=[{"trigger_name": "unexpected"}]))
