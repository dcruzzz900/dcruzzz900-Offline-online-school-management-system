import pytest

from postgres_migration_116_billing_payment_history import (
    MIGRATION_NAME, MIGRATION_SOURCE, MIGRATION_VERSION,
    apply_billing_payment_history, migration,
)
from postgres_migration_registry import POSTGRES_MIGRATIONS


class Result:
    def __init__(self, rows): self.rows = rows
    def fetchall(self): return self.rows
    def fetchone(self): return self.rows[0] if self.rows else None


class FakeConnection:
    def __init__(self, dependency_types=None, columns=None, fks=None, indexes=None, triggers=None):
        self.types = dependency_types or {"billing_payments": "bigint", "schools": "integer", "billing_invoices": "bigint"}
        types = {
            "id": "bigint", "payment_id": "bigint", "school_id": "integer", "invoice_id": "bigint",
            "action": "text", "old_status": "text", "new_status": "text", "old_amount_ngn": "double precision",
            "new_amount_ngn": "double precision", "old_reference": "text", "new_reference": "text",
            "actor": "text", "created_at": "text",
        }
        nullable = {"invoice_id", "old_status", "new_status", "old_amount_ngn", "new_amount_ngn", "old_reference", "new_reference", "actor"}
        self.columns = columns if columns is not None else [
            {"column_name": n, "data_type": t, "is_nullable": "YES" if n in nullable else "NO"} for n, t in types.items()
        ]
        self.fks = fks if fks is not None else [
            {"column_name": "payment_id", "foreign_table_name": "billing_payments", "foreign_column_name": "id"},
            {"column_name": "school_id", "foreign_table_name": "schools", "foreign_column_name": "id"},
            {"column_name": "invoice_id", "foreign_table_name": "billing_invoices", "foreign_column_name": "id"},
        ]
        self.indexes = indexes if indexes is not None else [
            {"indexname": "billing_payment_history_pkey", "indexdef": "CREATE UNIQUE INDEX billing_payment_history_pkey ON public.billing_payment_history USING btree (id)"},
            {"indexname": "idx_billing_payment_history_payment", "indexdef": "CREATE INDEX idx_billing_payment_history_payment ON public.billing_payment_history USING btree (payment_id, created_at)"},
            {"indexname": "idx_billing_payment_history_school", "indexdef": "CREATE INDEX idx_billing_payment_history_school ON public.billing_payment_history USING btree (school_id, created_at)"},
        ]
        self.triggers = triggers if triggers is not None else [
            {"trigger_name": "trg_billing_payment_history_no_update"},
            {"trigger_name": "trg_billing_payment_history_no_delete"},
        ]
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


def test_billing_payment_history_is_registered_in_order():
    assert MIGRATION_VERSION == 116
    assert MIGRATION_NAME == "create_billing_payment_history"
    assert [item.version for item in POSTGRES_MIGRATIONS] == list(range(100, 143))
    assert next(item for item in POSTGRES_MIGRATIONS if item.version == MIGRATION_VERSION).name == MIGRATION_NAME


def test_ddl_preserves_source_contract_and_immutable_guards():
    sql = MIGRATION_SOURCE.lower()
    for fragment in (
        "payment_id bigint not null", "school_id integer not null", "invoice_id bigint",
        "old_amount_ngn double precision", "new_amount_ngn double precision",
        "created_at text not null default current_timestamp", "references billing_payments(id)",
        "references schools(id)", "references billing_invoices(id)",
        "idx_billing_payment_history_payment on billing_payment_history (payment_id, created_at)",
        "idx_billing_payment_history_school on billing_payment_history (school_id, created_at)",
        "payment history records are immutable", "before update", "before delete",
    ):
        assert fragment in sql


def test_apply_validates_schema_foreign_keys_indexes_and_triggers():
    conn = FakeConnection()
    apply_billing_payment_history(conn)
    assert len(conn.calls) == 15


def test_apply_rejects_wrong_dependency_types_and_missing_columns():
    with pytest.raises(RuntimeError, match="billing_payments.id BIGINT"):
        apply_billing_payment_history(FakeConnection(dependency_types={"billing_payments": "integer", "schools": "integer", "billing_invoices": "bigint"}))
    with pytest.raises(RuntimeError, match="schools.id INTEGER"):
        apply_billing_payment_history(FakeConnection(dependency_types={"billing_payments": "bigint", "schools": "bigint", "billing_invoices": "bigint"}))
    with pytest.raises(RuntimeError, match="billing_invoices.id BIGINT"):
        apply_billing_payment_history(FakeConnection(dependency_types={"billing_payments": "bigint", "schools": "integer", "billing_invoices": "integer"}))
    columns = [r for r in FakeConnection().columns if r["column_name"] != "action"]
    with pytest.raises(RuntimeError, match="missing columns"):
        apply_billing_payment_history(FakeConnection(columns=columns))


def test_apply_rejects_wrong_foreign_keys_indexes_and_missing_triggers():
    with pytest.raises(RuntimeError, match="foreign keys are incompatible"):
        apply_billing_payment_history(FakeConnection(fks=[]))
    with pytest.raises(RuntimeError, match="indexes are incompatible"):
        apply_billing_payment_history(FakeConnection(indexes=FakeConnection().indexes[:-1]))
    with pytest.raises(RuntimeError, match="immutable triggers are missing"):
        apply_billing_payment_history(FakeConnection(triggers=[]))


def test_migration_metadata():
    item = migration()
    assert item.version == MIGRATION_VERSION
    assert item.name == MIGRATION_NAME
    assert item.source == MIGRATION_SOURCE
    assert callable(item.apply)
