import pytest

from postgres_migration_113_billing_invoices import (
    MIGRATION_NAME, MIGRATION_SOURCE, MIGRATION_VERSION,
    apply_billing_invoices, migration,
)
from postgres_migration_registry import POSTGRES_MIGRATIONS


class Result:
    def __init__(self, rows): self.rows = rows
    def fetchall(self): return self.rows
    def fetchone(self): return self.rows[0] if self.rows else None


class FakeConnection:
    def __init__(self, school_type="integer", columns=None, fks=None, indexes=None, triggers=None):
        self.school = None if school_type is None else {"data_type": school_type}
        types = {
            "id": "bigint", "school_id": "integer", "invoice_number": "text", "plan_code": "text",
            "amount_ngn": "double precision", "billing_days": "integer", "status": "text",
            "issued_at": "text", "due_at": "text", "paid_at": "text", "payment_reference": "text",
            "notes": "text", "created_by": "text",
        }
        nullable = {"due_at", "paid_at", "payment_reference", "notes", "created_by"}
        self.columns = columns if columns is not None else [
            {"column_name": n, "data_type": t, "is_nullable": "YES" if n in nullable else "NO"}
            for n, t in types.items()
        ]
        self.fks = fks if fks is not None else [
            {"column_name": "school_id", "foreign_table_name": "schools", "foreign_column_name": "id"}
        ]
        self.indexes = indexes if indexes is not None else [
            {"indexname": "billing_invoices_pkey", "indexdef": "CREATE UNIQUE INDEX billing_invoices_pkey ON public.billing_invoices USING btree (id)"},
            {"indexname": "uq_billing_invoices_invoice_number", "indexdef": "CREATE UNIQUE INDEX uq_billing_invoices_invoice_number ON public.billing_invoices USING btree (invoice_number)"},
            {"indexname": "idx_billing_invoices_status", "indexdef": "CREATE INDEX idx_billing_invoices_status ON public.billing_invoices USING btree (status)"},
            {"indexname": "idx_billing_invoices_school", "indexdef": "CREATE INDEX idx_billing_invoices_school ON public.billing_invoices USING btree (school_id)"},
        ]
        self.triggers = triggers or []
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        if "table_name = ? AND column_name = ?" in sql:
            return Result([self.school] if self.school else [])
        if "information_schema.columns" in sql: return Result(self.columns)
        if "information_schema.table_constraints" in sql: return Result(self.fks)
        if "FROM pg_indexes" in sql: return Result(self.indexes)
        if "information_schema.triggers" in sql: return Result(self.triggers)
        return Result([])


def test_billing_invoices_is_registered_in_order():
    assert MIGRATION_VERSION == 113
    assert MIGRATION_NAME == "create_billing_invoices"
    assert [item.version for item in POSTGRES_MIGRATIONS] == list(range(100, 188))
    assert next(item for item in POSTGRES_MIGRATIONS if item.version == MIGRATION_VERSION).name == MIGRATION_NAME


def test_ddl_preserves_source_contract_and_school_key_type():
    sql = MIGRATION_SOURCE.lower()
    for column in ("school_id", "invoice_number", "plan_code", "amount_ngn", "billing_days", "status", "issued_at", "due_at", "paid_at", "payment_reference", "notes", "created_by"):
        assert column in sql
    assert "school_id integer not null" in sql
    assert "amount_ngn double precision not null default 0" in sql
    assert "billing_days integer not null default 365" in sql
    assert "status text not null default 'pending'" in sql
    assert "unique (invoice_number)" in sql
    assert "foreign key (school_id) references schools(id)" in sql
    assert "idx_billing_invoices_status on billing_invoices (status)" in sql
    assert "idx_billing_invoices_school on billing_invoices (school_id)" in sql
    assert "create trigger" not in sql


def test_apply_validates_schema_foreign_key_and_indexes():
    conn = FakeConnection()
    apply_billing_invoices(conn)
    assert len(conn.calls) == 8


def test_apply_rejects_incompatible_school_key_and_missing_column():
    with pytest.raises(RuntimeError, match="schools.id INTEGER"):
        apply_billing_invoices(FakeConnection(school_type="bigint"))
    columns = [r for r in FakeConnection().columns if r["column_name"] != "invoice_number"]
    with pytest.raises(RuntimeError, match="missing columns"):
        apply_billing_invoices(FakeConnection(columns=columns))


def test_apply_rejects_wrong_foreign_key_indexes_and_triggers():
    with pytest.raises(RuntimeError, match="foreign keys are incompatible"):
        apply_billing_invoices(FakeConnection(fks=[]))
    with pytest.raises(RuntimeError, match="indexes are incompatible"):
        apply_billing_invoices(FakeConnection(indexes=FakeConnection().indexes[:-1]))
    with pytest.raises(RuntimeError, match="unexpected triggers"):
        apply_billing_invoices(FakeConnection(triggers=[{"trigger_name": "unexpected"}]))


def test_migration_metadata():
    item = migration()
    assert item.version == MIGRATION_VERSION
    assert item.name == MIGRATION_NAME
    assert item.source == MIGRATION_SOURCE
    assert callable(item.apply)
