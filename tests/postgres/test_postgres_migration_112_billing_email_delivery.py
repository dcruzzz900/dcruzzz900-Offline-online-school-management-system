import pytest

from postgres_migration_112_billing_email_delivery import (
    MIGRATION_NAME, MIGRATION_SOURCE, MIGRATION_VERSION,
    apply_billing_email_delivery, migration,
)
from postgres_migration_registry import POSTGRES_MIGRATIONS


class Result:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class FakeConnection:
    def __init__(self, school_type="integer", columns=None, fks=None, indexes=None, triggers=None):
        self.school = None if school_type is None else {"data_type": school_type}
        required = {"id", "school_id", "event_key", "recipient", "notification_type", "subject", "status", "attempt_count", "created_at", "updated_at"}
        types = {
            "id": "bigint", "school_id": "integer", "event_key": "text", "recipient": "text",
            "notification_type": "text", "subject": "text", "status": "text", "attempt_count": "integer",
            "last_error": "text", "sent_at": "text", "created_at": "text", "updated_at": "text",
        }
        self.columns = columns if columns is not None else [
            {"column_name": n, "data_type": t, "is_nullable": "NO" if n in required else "YES"}
            for n, t in types.items()
        ]
        self.fks = fks if fks is not None else [
            {"column_name": "school_id", "foreign_table_name": "schools", "foreign_column_name": "id"}
        ]
        self.indexes = indexes if indexes is not None else [
            {"indexname": "billing_email_delivery_pkey", "indexdef": "CREATE UNIQUE INDEX billing_email_delivery_pkey ON public.billing_email_delivery USING btree (id)"},
            {"indexname": "uq_billing_email_delivery_school_event", "indexdef": "CREATE UNIQUE INDEX uq_billing_email_delivery_school_event ON public.billing_email_delivery USING btree (school_id, event_key)"},
            {"indexname": "idx_billing_email_status", "indexdef": "CREATE INDEX idx_billing_email_status ON public.billing_email_delivery USING btree (status)"},
            {"indexname": "idx_billing_email_school", "indexdef": "CREATE INDEX idx_billing_email_school ON public.billing_email_delivery USING btree (school_id)"},
        ]
        self.triggers = triggers or []
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        if "table_name = ? AND column_name = ?" in sql:
            return Result([self.school] if self.school else [])
        if "information_schema.columns" in sql:
            return Result(self.columns)
        if "information_schema.table_constraints" in sql:
            return Result(self.fks)
        if "FROM pg_indexes" in sql:
            return Result(self.indexes)
        if "information_schema.triggers" in sql:
            return Result(self.triggers)
        return Result([])


def test_billing_email_delivery_is_registered_in_order():
    assert MIGRATION_VERSION == 112
    assert MIGRATION_NAME == "create_billing_email_delivery"
    assert [item.version for item in POSTGRES_MIGRATIONS] == list(range(100, 188))
    assert next(item for item in POSTGRES_MIGRATIONS if item.version == MIGRATION_VERSION).name == MIGRATION_NAME


def test_ddl_preserves_source_contract_and_school_key_type():
    sql = MIGRATION_SOURCE.lower()
    for column in ("school_id", "event_key", "recipient", "notification_type", "subject", "status", "attempt_count", "last_error", "sent_at", "created_at", "updated_at"):
        assert column in sql
    assert "school_id integer not null" in sql
    assert "status text not null default 'pending'" in sql
    assert "attempt_count integer not null default 0" in sql
    assert "unique (school_id, event_key)" in sql
    assert "foreign key (school_id) references schools(id)" in sql
    assert "idx_billing_email_status on billing_email_delivery (status)" in sql
    assert "idx_billing_email_school on billing_email_delivery (school_id)" in sql
    assert "create trigger" not in sql


def test_apply_validates_schema_foreign_key_and_indexes():
    conn = FakeConnection()
    apply_billing_email_delivery(conn)
    assert len(conn.calls) == 8  # school preflight, three DDL statements, four catalog checks


def test_apply_rejects_incompatible_school_key_and_schema():
    with pytest.raises(RuntimeError, match="schools.id INTEGER"):
        apply_billing_email_delivery(FakeConnection(school_type="bigint"))
    columns = [r for r in FakeConnection().columns if r["column_name"] != "event_key"]
    with pytest.raises(RuntimeError, match="missing columns"):
        apply_billing_email_delivery(FakeConnection(columns=columns))


def test_apply_rejects_wrong_foreign_key_indexes_and_triggers():
    with pytest.raises(RuntimeError, match="foreign keys are incompatible"):
        apply_billing_email_delivery(FakeConnection(fks=[]))
    with pytest.raises(RuntimeError, match="indexes are incompatible"):
        apply_billing_email_delivery(FakeConnection(indexes=FakeConnection().indexes[:-1]))
    with pytest.raises(RuntimeError, match="unexpected triggers"):
        apply_billing_email_delivery(FakeConnection(triggers=[{"trigger_name": "unexpected"}]))


def test_migration_metadata():
    item = migration()
    assert item.version == MIGRATION_VERSION
    assert item.name == MIGRATION_NAME
    assert item.source == MIGRATION_SOURCE
    assert callable(item.apply)
