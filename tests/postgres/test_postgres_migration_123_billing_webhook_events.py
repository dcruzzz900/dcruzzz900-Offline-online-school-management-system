import pytest

from postgres_migration_123_billing_webhook_events import (
    MIGRATION_NAME, MIGRATION_SOURCE, MIGRATION_VERSION,
    apply_billing_webhook_events, migration,
)
from postgres_migration_registry import POSTGRES_MIGRATIONS


class Result:
    def __init__(self, rows): self.rows = rows
    def fetchall(self): return self.rows
    def fetchone(self): return self.rows[0] if self.rows else None


class FakeConnection:
    def __init__(self, columns=None, indexes=None, triggers=None, fks=None):
        types = {
            "id": "bigint", "provider": "text", "provider_event_id": "text",
            "event_type": "text", "payment_reference": "text", "payload_hash": "text",
            "status": "text", "error_message": "text", "received_at": "text",
            "processed_at": "text",
        }
        nullable = {"event_type", "payment_reference", "error_message", "processed_at"}
        self.columns = columns if columns is not None else [
            {"column_name": n, "data_type": t, "is_nullable": "YES" if n in nullable else "NO"}
            for n, t in types.items()
        ]
        self.indexes = indexes if indexes is not None else [
            {"indexname": "billing_webhook_events_pkey", "indexdef": "CREATE UNIQUE INDEX billing_webhook_events_pkey ON public.billing_webhook_events USING btree (id)"},
            {"indexname": "idx_billing_webhook_reference", "indexdef": "CREATE INDEX idx_billing_webhook_reference ON public.billing_webhook_events USING btree (payment_reference)"},
            {"indexname": "idx_billing_webhook_event", "indexdef": "CREATE UNIQUE INDEX idx_billing_webhook_event ON public.billing_webhook_events USING btree (provider, provider_event_id)"},
        ]
        self.triggers = triggers if triggers is not None else []
        self.fks = fks if fks is not None else []
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        if "information_schema.columns" in sql: return Result(self.columns)
        if "information_schema.table_constraints" in sql: return Result(self.fks)
        if "FROM pg_indexes" in sql: return Result(self.indexes)
        if "information_schema.triggers" in sql: return Result(self.triggers)
        return Result([])


def test_billing_webhook_events_registered_in_order():
    assert MIGRATION_VERSION == 123
    assert MIGRATION_NAME == "create_billing_webhook_events"
    assert [item.version for item in POSTGRES_MIGRATIONS] == list(range(100, 188))
    assert next(item for item in POSTGRES_MIGRATIONS if item.version == 123).name == MIGRATION_NAME
    assert migration().version == 123


def test_ddl_preserves_columns_and_source_indexes():
    sql = MIGRATION_SOURCE.lower()
    for fragment in (
        "provider text not null", "provider_event_id text not null",
        "payload_hash text not null", "status text not null default 'received'",
        "received_at text not null default current_timestamp",
        "idx_billing_webhook_reference on billing_webhook_events (payment_reference)",
        "create unique index if not exists idx_billing_webhook_event on billing_webhook_events (provider, provider_event_id)",
    ):
        assert fragment in sql


def test_apply_validates_and_executes_migration():
    conn = FakeConnection()
    apply_billing_webhook_events(conn)
    assert any("CREATE TABLE IF NOT EXISTS billing_webhook_events" in sql for sql, _ in conn.calls)


def test_apply_rejects_missing_column():
    columns = [r for r in FakeConnection().columns if r["column_name"] != "payload_hash"]
    with pytest.raises(RuntimeError, match="missing columns"):
        apply_billing_webhook_events(FakeConnection(columns=columns))


def test_apply_rejects_incompatible_column_type():
    columns = [dict(r) for r in FakeConnection().columns]
    next(r for r in columns if r["column_name"] == "provider_event_id")["data_type"] = "varchar"
    with pytest.raises(RuntimeError, match="incompatible columns"):
        apply_billing_webhook_events(FakeConnection(columns=columns))


def test_apply_rejects_unexpected_foreign_key():
    with pytest.raises(RuntimeError, match="unexpected foreign keys"):
        apply_billing_webhook_events(FakeConnection(fks=[{"constraint_name": "unexpected_fk"}]))


def test_apply_rejects_missing_or_incompatible_indexes():
    indexes = [r for r in FakeConnection().indexes if r["indexname"] != "idx_billing_webhook_event"]
    with pytest.raises(RuntimeError, match="indexes"):
        apply_billing_webhook_events(FakeConnection(indexes=indexes))


def test_apply_rejects_unexpected_trigger():
    with pytest.raises(RuntimeError, match="unexpected triggers"):
        apply_billing_webhook_events(FakeConnection(triggers=[{"trigger_name": "unexpected_trigger"}]))
