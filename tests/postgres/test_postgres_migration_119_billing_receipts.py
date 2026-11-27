import pytest

from postgres_migration_119_billing_receipts import (
    MIGRATION_NAME, MIGRATION_SOURCE, MIGRATION_VERSION,
    apply_billing_receipts, migration,
)
from postgres_migration_registry import POSTGRES_MIGRATIONS


class Result:
    def __init__(self, rows): self.rows = rows
    def fetchall(self): return self.rows
    def fetchone(self): return self.rows[0] if self.rows else None


class FakeConnection:
    def __init__(self, dependency_types=None, columns=None, fks=None, indexes=None, triggers=None):
        self.types = dependency_types or {"schools": "integer", "billing_invoices": "bigint", "billing_payments": "bigint"}
        types = {"id": "bigint", "school_id": "integer", "invoice_id": "bigint", "payment_id": "bigint",
                 "receipt_number": "text", "amount_ngn": "double precision", "currency": "text",
                 "provider": "text", "payment_reference": "text", "issued_at": "text"}
        nullable = {"invoice_id"}
        self.columns = columns if columns is not None else [
            {"column_name": n, "data_type": t, "is_nullable": "YES" if n in nullable else "NO"} for n, t in types.items()]
        self.fks = fks if fks is not None else [
            {"column_name": c, "foreign_table_name": t, "foreign_column_name": "id"}
            for c, t in (("school_id", "schools"), ("invoice_id", "billing_invoices"), ("payment_id", "billing_payments"))]
        self.indexes = indexes if indexes is not None else [
            {"indexname": "billing_receipts_pkey", "indexdef": "CREATE UNIQUE INDEX billing_receipts_pkey ON public.billing_receipts USING btree (id)"},
            {"indexname": "billing_receipts_payment_id_key", "indexdef": "CREATE UNIQUE INDEX billing_receipts_payment_id_key ON public.billing_receipts USING btree (payment_id)"},
            {"indexname": "billing_receipts_receipt_number_key", "indexdef": "CREATE UNIQUE INDEX billing_receipts_receipt_number_key ON public.billing_receipts USING btree (receipt_number)"},
            {"indexname": "idx_billing_receipts_invoice", "indexdef": "CREATE INDEX idx_billing_receipts_invoice ON public.billing_receipts USING btree (invoice_id)"},
            {"indexname": "idx_billing_receipts_school", "indexdef": "CREATE INDEX idx_billing_receipts_school ON public.billing_receipts USING btree (school_id)"},
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


def test_billing_receipts_registered_in_order():
    assert MIGRATION_VERSION == 119
    assert MIGRATION_NAME == "create_billing_receipts"
    assert [item.version for item in POSTGRES_MIGRATIONS] == list(range(100, 188))
    assert next(item for item in POSTGRES_MIGRATIONS if item.version == MIGRATION_VERSION).name == MIGRATION_NAME
    assert migration().version == 119


def test_ddl_preserves_source_columns_constraints_and_indexes():
    sql = MIGRATION_SOURCE.lower()
    for fragment in (
        "school_id integer not null", "invoice_id bigint", "payment_id bigint not null unique",
        "receipt_number text not null unique", "amount_ngn double precision not null default 0",
        "currency text not null default 'ngn'", "provider text not null default 'manual'",
        "issued_at text not null default current_timestamp", "references schools(id)",
        "references billing_invoices(id)", "references billing_payments(id)",
        "idx_billing_receipts_invoice on billing_receipts (invoice_id)",
        "idx_billing_receipts_school on billing_receipts (school_id)",
    ):
        assert fragment in sql


def test_apply_validates_and_executes_migration():
    conn = FakeConnection()
    apply_billing_receipts(conn)
    assert any("CREATE TABLE IF NOT EXISTS billing_receipts" in sql for sql, _ in conn.calls)


@pytest.mark.parametrize("dependency,wrong_type", [
    ("schools", "bigint"), ("billing_invoices", "integer"), ("billing_payments", "integer")])
def test_apply_rejects_incompatible_dependency_key_type(dependency, wrong_type):
    types = {"schools": "integer", "billing_invoices": "bigint", "billing_payments": "bigint"}
    types[dependency] = wrong_type
    with pytest.raises(RuntimeError, match="requires"):
        apply_billing_receipts(FakeConnection(dependency_types=types))


def test_apply_rejects_missing_foreign_key():
    with pytest.raises(RuntimeError, match="foreign keys"):
        apply_billing_receipts(FakeConnection(fks=[]))


def test_apply_rejects_missing_unique_index():
    conn = FakeConnection(indexes=[r for r in FakeConnection().indexes if r["indexname"] != "billing_receipts_payment_id_key"])
    with pytest.raises(RuntimeError, match="indexes"):
        apply_billing_receipts(conn)


def test_apply_rejects_unexpected_trigger():
    with pytest.raises(RuntimeError, match="unexpected triggers"):
        apply_billing_receipts(FakeConnection(triggers=[{"trigger_name": "unexpected"}]))
