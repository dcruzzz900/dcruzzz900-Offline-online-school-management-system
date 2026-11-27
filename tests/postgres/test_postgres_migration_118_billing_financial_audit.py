import pytest

from postgres_migration_118_billing_financial_audit import (
    MIGRATION_NAME, MIGRATION_SOURCE, MIGRATION_VERSION,
    apply_billing_financial_audit, migration,
)
from postgres_migration_registry import POSTGRES_MIGRATIONS


class Result:
    def __init__(self, rows): self.rows = rows
    def fetchall(self): return self.rows
    def fetchone(self): return self.rows[0] if self.rows else None


class FakeConnection:
    def __init__(self, dependency_types=None, columns=None, fks=None, indexes=None, triggers=None):
        self.types = dependency_types or {"schools": "integer", "billing_payments": "bigint", "billing_invoices": "bigint"}
        types = {"id": "bigint", "event_type": "text", "actor_type": "text", "actor_name": "text",
                 "school_id": "integer", "payment_id": "bigint", "invoice_id": "bigint", "reference": "text",
                 "details": "text", "created_at": "text"}
        nullable = {"actor_name", "school_id", "payment_id", "invoice_id", "reference", "details"}
        self.columns = columns if columns is not None else [
            {"column_name": n, "data_type": t, "is_nullable": "YES" if n in nullable else "NO"} for n, t in types.items()]
        self.fks = fks if fks is not None else [
            {"column_name": c, "foreign_table_name": t, "foreign_column_name": "id"}
            for c, t in (("school_id", "schools"), ("payment_id", "billing_payments"), ("invoice_id", "billing_invoices"))]
        self.indexes = indexes if indexes is not None else [
            {"indexname": "billing_financial_audit_pkey", "indexdef": "CREATE UNIQUE INDEX billing_financial_audit_pkey ON public.billing_financial_audit USING btree (id)"},
            *[{"indexname": n, "indexdef": f"CREATE INDEX {n} ON public.billing_financial_audit USING btree ({c})"}
              for n, c in (("idx_billing_fin_audit_invoice", "invoice_id"), ("idx_billing_fin_audit_payment", "payment_id"),
                           ("idx_billing_fin_audit_school", "school_id"), ("idx_billing_fin_audit_created", "created_at"))]]
        self.triggers = triggers if triggers is not None else [
            {"trigger_name": "trg_billing_financial_audit_no_update"}, {"trigger_name": "trg_billing_financial_audit_no_delete"}]
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


def test_billing_financial_audit_registered_in_order():
    assert MIGRATION_VERSION == 118
    assert MIGRATION_NAME == "create_billing_financial_audit"
    assert [item.version for item in POSTGRES_MIGRATIONS] == list(range(100, 188))
    assert next(item for item in POSTGRES_MIGRATIONS if item.version == MIGRATION_VERSION).name == MIGRATION_NAME


def test_ddl_preserves_source_contract_indexes_and_immutability():
    sql = MIGRATION_SOURCE.lower()
    for fragment in (
        "event_type text not null", "actor_type text not null", "school_id integer", "payment_id bigint",
        "invoice_id bigint", "created_at text not null default current_timestamp", "references schools(id)",
        "references billing_payments(id)", "references billing_invoices(id)",
        "idx_billing_fin_audit_invoice on billing_financial_audit (invoice_id)",
        "idx_billing_fin_audit_payment on billing_financial_audit (payment_id)",
        "idx_billing_fin_audit_school on billing_financial_audit (school_id)",
        "idx_billing_fin_audit_created on billing_financial_audit (created_at)",
        "trg_billing_financial_audit_no_update", "trg_billing_financial_audit_no_delete",
        "financial audit records are immutable",
    ):
        assert fragment in sql


def test_apply_validates_and_executes_migration():
    conn = FakeConnection()
    apply_billing_financial_audit(conn)
    assert any("CREATE TABLE IF NOT EXISTS billing_financial_audit" in sql for sql, _ in conn.calls)


@pytest.mark.parametrize("dependency,wrong_type", [("schools", "bigint"), ("billing_payments", "integer"), ("billing_invoices", "integer")])
def test_apply_rejects_incompatible_dependency_key_type(dependency, wrong_type):
    types = {"schools": "integer", "billing_payments": "bigint", "billing_invoices": "bigint"}
    types[dependency] = wrong_type
    with pytest.raises(RuntimeError, match="requires"):
        apply_billing_financial_audit(FakeConnection(dependency_types=types))


def test_apply_rejects_missing_foreign_key():
    with pytest.raises(RuntimeError, match="foreign keys"):
        apply_billing_financial_audit(FakeConnection(fks=[]))


def test_apply_rejects_missing_immutable_trigger():
    with pytest.raises(RuntimeError, match="immutable triggers"):
        apply_billing_financial_audit(FakeConnection(triggers=[]))
