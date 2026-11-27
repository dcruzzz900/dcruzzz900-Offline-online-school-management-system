import pytest

from postgres_migration_120_billing_reconciliation_exceptions import (
    MIGRATION_NAME, MIGRATION_SOURCE, MIGRATION_VERSION,
    apply_billing_reconciliation_exceptions, migration,
)
from postgres_migration_registry import POSTGRES_MIGRATIONS


class Result:
    def __init__(self, rows): self.rows = rows
    def fetchall(self): return self.rows
    def fetchone(self): return self.rows[0] if self.rows else None


class FakeConnection:
    def __init__(self, dependency_types=None, columns=None, fks=None, indexes=None, triggers=None):
        self.types = dependency_types or {"billing_payments": "bigint", "billing_invoices": "bigint"}
        types = {"id": "bigint", "exception_key": "text", "exception_type": "text", "payment_id": "bigint",
                 "invoice_id": "bigint", "reference": "text", "details": "text", "status": "text",
                 "reviewed_by": "text", "reviewed_at": "text", "review_note": "text", "created_at": "text"}
        nullable = {"payment_id", "invoice_id", "reference", "reviewed_by", "reviewed_at", "review_note"}
        self.columns = columns if columns is not None else [
            {"column_name": n, "data_type": t, "is_nullable": "YES" if n in nullable else "NO"} for n, t in types.items()]
        self.fks = fks if fks is not None else [
            {"column_name": c, "foreign_table_name": t, "foreign_column_name": "id"}
            for c, t in (("payment_id", "billing_payments"), ("invoice_id", "billing_invoices"))]
        self.indexes = indexes if indexes is not None else [
            {"indexname": "billing_reconciliation_exceptions_pkey", "indexdef": "CREATE UNIQUE INDEX billing_reconciliation_exceptions_pkey ON public.billing_reconciliation_exceptions USING btree (id)"},
            {"indexname": "billing_reconciliation_exceptions_exception_key_key", "indexdef": "CREATE UNIQUE INDEX billing_reconciliation_exceptions_exception_key_key ON public.billing_reconciliation_exceptions USING btree (exception_key)"},
            {"indexname": "idx_billing_recon_invoice", "indexdef": "CREATE INDEX idx_billing_recon_invoice ON public.billing_reconciliation_exceptions USING btree (invoice_id)"},
            {"indexname": "idx_billing_recon_payment", "indexdef": "CREATE INDEX idx_billing_recon_payment ON public.billing_reconciliation_exceptions USING btree (payment_id)"},
            {"indexname": "idx_billing_recon_status", "indexdef": "CREATE INDEX idx_billing_recon_status ON public.billing_reconciliation_exceptions USING btree (status)"},
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


def test_billing_reconciliation_exceptions_registered_in_order():
    assert MIGRATION_VERSION == 120
    assert MIGRATION_NAME == "create_billing_reconciliation_exceptions"
    assert [item.version for item in POSTGRES_MIGRATIONS] == list(range(100, 188))
    assert next(item for item in POSTGRES_MIGRATIONS if item.version == 120).name == MIGRATION_NAME
    assert migration().version == 120


def test_ddl_preserves_source_columns_constraints_and_indexes():
    sql = MIGRATION_SOURCE.lower()
    for fragment in (
        "exception_key text not null unique", "exception_type text not null", "payment_id bigint",
        "invoice_id bigint", "details text not null default ''", "status text not null default 'open'",
        "created_at text not null default current_timestamp", "references billing_payments(id)",
        "references billing_invoices(id)", "idx_billing_recon_invoice on billing_reconciliation_exceptions (invoice_id)",
        "idx_billing_recon_payment on billing_reconciliation_exceptions (payment_id)",
        "idx_billing_recon_status on billing_reconciliation_exceptions (status)",
    ):
        assert fragment in sql


def test_apply_validates_and_executes_migration():
    conn = FakeConnection()
    apply_billing_reconciliation_exceptions(conn)
    assert any("CREATE TABLE IF NOT EXISTS billing_reconciliation_exceptions" in sql for sql, _ in conn.calls)


@pytest.mark.parametrize("dependency", ["billing_payments", "billing_invoices"])
def test_apply_rejects_incompatible_dependency_key_type(dependency):
    types = {"billing_payments": "bigint", "billing_invoices": "bigint"}
    types[dependency] = "integer"
    with pytest.raises(RuntimeError, match="requires"):
        apply_billing_reconciliation_exceptions(FakeConnection(dependency_types=types))


def test_apply_rejects_missing_foreign_key():
    with pytest.raises(RuntimeError, match="foreign keys"):
        apply_billing_reconciliation_exceptions(FakeConnection(fks=[]))


def test_apply_rejects_missing_lookup_index():
    indexes = [r for r in FakeConnection().indexes if r["indexname"] != "idx_billing_recon_status"]
    with pytest.raises(RuntimeError, match="indexes"):
        apply_billing_reconciliation_exceptions(FakeConnection(indexes=indexes))


def test_apply_rejects_missing_unique_key_index():
    indexes = [r for r in FakeConnection().indexes if r["indexname"] != "billing_reconciliation_exceptions_exception_key_key"]
    with pytest.raises(RuntimeError, match="indexes"):
        apply_billing_reconciliation_exceptions(FakeConnection(indexes=indexes))


def test_apply_rejects_unexpected_trigger():
    with pytest.raises(RuntimeError, match="unexpected triggers"):
        apply_billing_reconciliation_exceptions(FakeConnection(triggers=[{"trigger_name": "unexpected"}]))
