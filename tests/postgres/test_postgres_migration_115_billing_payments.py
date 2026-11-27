import pytest

from postgres_migration_115_billing_payments import (
    MIGRATION_NAME, MIGRATION_SOURCE, MIGRATION_VERSION,
    apply_billing_payments, migration,
)
from postgres_migration_registry import POSTGRES_MIGRATIONS


class Result:
    def __init__(self, rows): self.rows = rows
    def fetchall(self): return self.rows
    def fetchone(self): return self.rows[0] if self.rows else None


class FakeConnection:
    def __init__(self, school_type="integer", invoice_type="bigint", columns=None, fks=None, indexes=None, triggers=None):
        self.types = {"schools": school_type, "billing_invoices": invoice_type}
        types = {"id": "bigint", "school_id": "integer", "invoice_id": "bigint", "provider": "text",
                 "payment_reference": "text", "amount_ngn": "double precision", "currency": "text", "status": "text",
                 "paid_at": "text", "confirmed_at": "text", "confirmed_by": "text", "raw_metadata": "text", "created_at": "text"}
        nullable = {"invoice_id", "paid_at", "confirmed_at", "confirmed_by"}
        self.columns = columns if columns is not None else [
            {"column_name": n, "data_type": t, "is_nullable": "YES" if n in nullable else "NO"} for n, t in types.items()
        ]
        self.fks = fks if fks is not None else [
            {"column_name": "school_id", "foreign_table_name": "schools", "foreign_column_name": "id"},
            {"column_name": "invoice_id", "foreign_table_name": "billing_invoices", "foreign_column_name": "id"},
        ]
        self.indexes = indexes if indexes is not None else [
            {"indexname": "billing_payments_pkey", "indexdef": "CREATE UNIQUE INDEX billing_payments_pkey ON public.billing_payments USING btree (id)"},
            {"indexname": "idx_billing_payments_reference", "indexdef": "CREATE UNIQUE INDEX idx_billing_payments_reference ON public.billing_payments USING btree (payment_reference)"},
            {"indexname": "idx_billing_payments_status", "indexdef": "CREATE INDEX idx_billing_payments_status ON public.billing_payments USING btree (status)"},
            {"indexname": "idx_billing_payments_school", "indexdef": "CREATE INDEX idx_billing_payments_school ON public.billing_payments USING btree (school_id)"},
        ]
        self.triggers = triggers or []
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        if "table_name = ? AND column_name = ?" in sql:
            table = params[0]
            value = self.types.get(table)
            return Result([{"data_type": value}] if value else [])
        if "information_schema.columns" in sql: return Result(self.columns)
        if "information_schema.table_constraints" in sql: return Result(self.fks)
        if "FROM pg_indexes" in sql: return Result(self.indexes)
        if "information_schema.triggers" in sql: return Result(self.triggers)
        return Result([])


def test_billing_payments_is_registered_in_order():
    assert MIGRATION_VERSION == 115
    assert MIGRATION_NAME == "create_billing_payments"
    assert [item.version for item in POSTGRES_MIGRATIONS] == list(range(100, 188))
    assert next(item for item in POSTGRES_MIGRATIONS if item.version == MIGRATION_VERSION).name == MIGRATION_NAME


def test_ddl_preserves_source_contract_and_dependency_types():
    sql = MIGRATION_SOURCE.lower()
    for fragment in (
        "school_id integer not null", "invoice_id bigint", "provider text not null default 'manual'",
        "payment_reference text not null", "amount_ngn double precision not null default 0",
        "currency text not null default 'ngn'", "status text not null default 'pending'",
        "raw_metadata text not null default '{}'", "created_at text not null default current_timestamp",
        "references schools(id)", "references billing_invoices(id)",
        "create unique index if not exists idx_billing_payments_reference on billing_payments (payment_reference)", "idx_billing_payments_status on billing_payments (status)",
        "idx_billing_payments_school on billing_payments (school_id)",
    ):
        assert fragment in sql
    assert "create trigger" not in sql


def test_apply_validates_schema_foreign_keys_and_indexes():
    conn = FakeConnection()
    apply_billing_payments(conn)
    assert len(conn.calls) == 10


def test_apply_rejects_wrong_dependency_types_and_missing_columns():
    with pytest.raises(RuntimeError, match="schools.id INTEGER"):
        apply_billing_payments(FakeConnection(school_type="bigint"))
    with pytest.raises(RuntimeError, match="billing_invoices.id BIGINT"):
        apply_billing_payments(FakeConnection(invoice_type="integer"))
    columns = [r for r in FakeConnection().columns if r["column_name"] != "payment_reference"]
    with pytest.raises(RuntimeError, match="missing columns"):
        apply_billing_payments(FakeConnection(columns=columns))


def test_apply_rejects_wrong_foreign_keys_indexes_and_triggers():
    with pytest.raises(RuntimeError, match="foreign keys are incompatible"):
        apply_billing_payments(FakeConnection(fks=[]))
    with pytest.raises(RuntimeError, match="indexes are incompatible"):
        apply_billing_payments(FakeConnection(indexes=FakeConnection().indexes[:-1]))
    with pytest.raises(RuntimeError, match="unexpected triggers"):
        apply_billing_payments(FakeConnection(triggers=[{"trigger_name": "unexpected"}]))


def test_migration_metadata():
    item = migration()
    assert item.version == MIGRATION_VERSION
    assert item.name == MIGRATION_NAME
    assert item.source == MIGRATION_SOURCE
    assert callable(item.apply)
