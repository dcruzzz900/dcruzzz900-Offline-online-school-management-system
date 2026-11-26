import pytest

from postgres_migration_117_billing_adjustments import (
    MIGRATION_NAME, MIGRATION_SOURCE, MIGRATION_VERSION,
    apply_billing_adjustments, migration,
)
from postgres_migration_registry import POSTGRES_MIGRATIONS


class Result:
    def __init__(self, rows): self.rows = rows
    def fetchall(self): return self.rows
    def fetchone(self): return self.rows[0] if self.rows else None


class FakeConnection:
    def __init__(self, dependency_types=None, columns=None, fks=None, indexes=None, triggers=None):
        self.types = dependency_types or {"schools": "integer", "billing_payments": "bigint", "billing_invoices": "bigint"}
        types = {
            "id": "bigint", "school_id": "integer", "payment_id": "bigint", "invoice_id": "bigint",
            "adjustment_type": "text", "amount_ngn": "double precision", "status": "text", "reason": "text",
            "reference": "text", "requested_by": "text", "approved_by": "text", "rejected_by": "text",
            "processed_by": "text", "requested_at": "text", "approved_at": "text", "rejected_at": "text",
            "processed_at": "text", "external_reference": "text",
        }
        nullable = {"invoice_id", "requested_by", "approved_by", "rejected_by", "processed_by", "approved_at", "rejected_at", "processed_at", "external_reference"}
        self.columns = columns if columns is not None else [
            {"column_name": n, "data_type": t, "is_nullable": "YES" if n in nullable else "NO"} for n, t in types.items()
        ]
        self.fks = fks if fks is not None else [
            {"column_name": "school_id", "foreign_table_name": "schools", "foreign_column_name": "id"},
            {"column_name": "payment_id", "foreign_table_name": "billing_payments", "foreign_column_name": "id"},
            {"column_name": "invoice_id", "foreign_table_name": "billing_invoices", "foreign_column_name": "id"},
        ]
        self.indexes = indexes if indexes is not None else [
            {"indexname": "billing_adjustments_pkey", "indexdef": "CREATE UNIQUE INDEX billing_adjustments_pkey ON public.billing_adjustments USING btree (id)"},
            {"indexname": "billing_adjustments_reference_key", "indexdef": "CREATE UNIQUE INDEX billing_adjustments_reference_key ON public.billing_adjustments USING btree (reference)"},
            {"indexname": "idx_billing_adjustments_payment", "indexdef": "CREATE INDEX idx_billing_adjustments_payment ON public.billing_adjustments USING btree (payment_id)"},
            {"indexname": "idx_billing_adjustments_status", "indexdef": "CREATE INDEX idx_billing_adjustments_status ON public.billing_adjustments USING btree (status)"},
        ]
        self.triggers = triggers or []
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


def test_billing_adjustments_is_registered_in_order():
    assert MIGRATION_VERSION == 117
    assert MIGRATION_NAME == "create_billing_adjustments"
    assert [item.version for item in POSTGRES_MIGRATIONS] == list(range(100, 143))
    assert next(item for item in POSTGRES_MIGRATIONS if item.version == MIGRATION_VERSION).name == MIGRATION_NAME


def test_ddl_preserves_source_contract_and_dependencies():
    sql = MIGRATION_SOURCE.lower()
    for fragment in (
        "school_id integer not null", "payment_id bigint not null", "invoice_id bigint",
        "amount_ngn double precision not null", "status text not null default 'requested'",
        "reference text not null unique", "requested_at text not null default current_timestamp",
        "references schools(id)", "references billing_payments(id)", "references billing_invoices(id)",
        "idx_billing_adjustments_payment on billing_adjustments (payment_id)",
        "idx_billing_adjustments_status on billing_adjustments (status)",
    ):
        assert fragment in sql


def test_apply_validates_and_executes_migration():
    conn = FakeConnection()
    apply_billing_adjustments(conn)
    assert any("CREATE TABLE IF NOT EXISTS billing_adjustments" in sql for sql, _ in conn.calls)


@pytest.mark.parametrize("dependency,wrong_type", [("schools", "bigint"), ("billing_payments", "integer"), ("billing_invoices", "integer")])
def test_apply_rejects_incompatible_dependency_key_type(dependency, wrong_type):
    types = {"schools": "integer", "billing_payments": "bigint", "billing_invoices": "bigint"}
    types[dependency] = wrong_type
    with pytest.raises(RuntimeError, match="requires"):
        apply_billing_adjustments(FakeConnection(dependency_types=types))


def test_apply_rejects_missing_foreign_key():
    conn = FakeConnection(fks=[])
    with pytest.raises(RuntimeError, match="foreign keys"):
        apply_billing_adjustments(conn)


def test_apply_rejects_unexpected_trigger():
    conn = FakeConnection(triggers=[{"trigger_name": "unexpected"}])
    with pytest.raises(RuntimeError, match="unexpected triggers"):
        apply_billing_adjustments(conn)
