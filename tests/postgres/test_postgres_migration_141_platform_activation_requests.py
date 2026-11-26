import pytest

from postgres_migration_141_platform_activation_requests import (
    MIGRATION_NAME, MIGRATION_SOURCE, MIGRATION_VERSION,
    apply_platform_activation_requests, migration,
)
from postgres_migration_registry import POSTGRES_MIGRATIONS


class Result:
    def __init__(self, rows): self.rows = rows
    def fetchall(self): return self.rows


class FakeConnection:
    def __init__(self, columns=None, constraints=None, indexes=None, triggers=None):
        expected = {
            "id": ("bigint", True), "school_id": ("integer", True),
            "status": ("text", True), "submitted_at": ("text", False),
            "approved_by": ("text", False), "approved_at": ("text", False),
            "activation_code_delivery_channel": ("text", False),
            "activation_code_delivery_status": ("text", False),
            "activation_code_sent_at": ("text", False),
        }
        self.columns = columns if columns is not None else [
            {"column_name": n, "data_type": t, "is_nullable": "NO" if required else "YES"}
            for n, (t, required) in expected.items()
        ]
        self.constraints = constraints if constraints is not None else [
            {"conname": "platform_activation_requests_pkey", "contype": "p", "definition": "PRIMARY KEY (id)"},
            {"conname": "platform_activation_requests_school_id_fkey", "contype": "f", "definition": "FOREIGN KEY (school_id) REFERENCES schools(id)"},
        ]
        self.indexes = indexes if indexes is not None else [
            {"indexname": "platform_activation_requests_pkey", "indexdef": "CREATE UNIQUE INDEX platform_activation_requests_pkey ON public.platform_activation_requests USING btree (id)"},
            {"indexname": "idx_platform_activation_requests_status", "indexdef": "CREATE INDEX idx_platform_activation_requests_status ON public.platform_activation_requests USING btree (status, submitted_at)"},
        ]
        self.triggers = triggers or []
        self.statements = []

    def execute(self, sql, params=()):
        self.statements.append(sql)
        if "information_schema.columns" in sql: return Result(self.columns)
        if "FROM pg_constraint" in sql: return Result(self.constraints)
        if "FROM pg_indexes" in sql: return Result(self.indexes)
        if "information_schema.triggers" in sql: return Result(self.triggers)
        return Result([])


def test_registry_and_metadata():
    assert MIGRATION_VERSION == 141
    assert MIGRATION_NAME == "create_platform_activation_requests"
    assert [item.version for item in POSTGRES_MIGRATIONS] == list(range(100, 143))
    assert next(item for item in POSTGRES_MIGRATIONS if item.version == 141).name == MIGRATION_NAME
    assert migration().version == 141
    assert "REFERENCES schools(id)" in MIGRATION_SOURCE


def test_apply_creates_and_validates_table():
    conn = FakeConnection()
    apply_platform_activation_requests(conn)
    assert any("CREATE TABLE IF NOT EXISTS platform_activation_requests" in sql for sql in conn.statements)
    assert any("idx_platform_activation_requests_status" in sql for sql in conn.statements)


def test_apply_rejects_wrong_columns():
    with pytest.raises(RuntimeError, match="columns incompatible"):
        apply_platform_activation_requests(FakeConnection(columns=[]))


def test_apply_rejects_wrong_constraints_or_school_foreign_key():
    constraints = FakeConnection().constraints.copy()
    constraints[1] = {**constraints[1], "definition": "FOREIGN KEY (school_id) REFERENCES users(id)"}
    with pytest.raises(RuntimeError, match="school foreign key incompatible"):
        apply_platform_activation_requests(FakeConnection(constraints=constraints))


def test_apply_rejects_missing_school_foreign_key():
    with pytest.raises(RuntimeError, match="constraints incompatible"):
        apply_platform_activation_requests(FakeConnection(constraints=[]))


def test_apply_rejects_wrong_indexes():
    with pytest.raises(RuntimeError, match="indexes incompatible"):
        apply_platform_activation_requests(FakeConnection(indexes=[]))


def test_apply_rejects_wrong_status_index_definition():
    indexes = FakeConnection().indexes.copy()
    indexes[1] = {**indexes[1], "indexdef": "CREATE INDEX idx_platform_activation_requests_status ON public.platform_activation_requests USING btree (status)"}
    with pytest.raises(RuntimeError, match="status index incompatible"):
        apply_platform_activation_requests(FakeConnection(indexes=indexes))


def test_apply_rejects_triggers():
    with pytest.raises(RuntimeError, match="must not have triggers"):
        apply_platform_activation_requests(FakeConnection(triggers=[{"trigger_name": "unexpected"}]))
