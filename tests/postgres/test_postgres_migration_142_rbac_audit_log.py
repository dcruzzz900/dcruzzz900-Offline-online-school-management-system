import pytest

from postgres_migration_142_rbac_audit_log import (
    MIGRATION_NAME, MIGRATION_SOURCE, MIGRATION_VERSION,
    apply_rbac_audit_log, migration,
)
from postgres_migration_registry import POSTGRES_MIGRATIONS


class Result:
    def __init__(self, rows): self.rows = rows
    def fetchall(self): return self.rows


class FakeConnection:
    def __init__(self, columns=None, constraints=None, indexes=None, triggers=None):
        expected = {
            "id": ("bigint", True), "created_at": ("text", False),
            "actor_type": ("text", False), "actor_id": ("bigint", False),
            "actor_name": ("text", False), "actor_role": ("text", False),
            "school_id": ("integer", False), "tenant_id": ("text", False),
            "action": ("text", True), "entity_type": ("text", False),
            "entity_id": ("text", False), "changes": ("text", False),
            "ip_address": ("text", False),
        }
        self.columns = columns if columns is not None else [
            {"column_name": n, "data_type": t, "is_nullable": "NO" if required else "YES"}
            for n, (t, required) in expected.items()
        ]
        self.constraints = constraints if constraints is not None else [
            {"conname": "rbac_audit_log_pkey", "contype": "p"}
        ]
        self.indexes = indexes if indexes is not None else [
            {"indexname": "rbac_audit_log_pkey", "indexdef": "CREATE UNIQUE INDEX rbac_audit_log_pkey ON public.rbac_audit_log USING btree (id)"},
            {"indexname": "idx_rbac_audit_school", "indexdef": "CREATE INDEX idx_rbac_audit_school ON public.rbac_audit_log USING btree (school_id, created_at)"},
        ]
        self.triggers = triggers if triggers is not None else [
            {"trigger_name": "trg_rbac_audit_log_no_update"},
            {"trigger_name": "trg_rbac_audit_log_no_delete"},
        ]
        self.statements = []

    def execute(self, sql, params=()):
        self.statements.append(sql)
        if "information_schema.columns" in sql: return Result(self.columns)
        if "FROM pg_constraint" in sql: return Result(self.constraints)
        if "FROM pg_indexes" in sql: return Result(self.indexes)
        if "information_schema.triggers" in sql: return Result(self.triggers)
        return Result([])


def test_registry_and_metadata():
    assert MIGRATION_VERSION == 142
    assert MIGRATION_NAME == "create_rbac_audit_log"
    assert [item.version for item in POSTGRES_MIGRATIONS] == list(range(100, 143))
    assert next(item for item in POSTGRES_MIGRATIONS if item.version == 142).name == MIGRATION_NAME
    assert migration().version == 142
    assert "action TEXT NOT NULL" in MIGRATION_SOURCE


def test_apply_creates_table_index_and_append_only_triggers():
    conn = FakeConnection()
    apply_rbac_audit_log(conn)
    assert any("CREATE TABLE IF NOT EXISTS rbac_audit_log" in s for s in conn.statements)
    assert any("idx_rbac_audit_school" in s for s in conn.statements)
    assert any("trg_rbac_audit_log_no_update" in s for s in conn.statements)
    assert any("trg_rbac_audit_log_no_delete" in s for s in conn.statements)


def test_apply_rejects_wrong_columns():
    with pytest.raises(RuntimeError, match="columns incompatible"):
        apply_rbac_audit_log(FakeConnection(columns=[]))


def test_apply_rejects_unexpected_constraints():
    with pytest.raises(RuntimeError, match="constraints incompatible"):
        apply_rbac_audit_log(FakeConnection(constraints=[]))


def test_apply_rejects_wrong_index_definition():
    indexes = FakeConnection().indexes.copy()
    indexes[1] = {**indexes[1], "indexdef": "CREATE INDEX idx_rbac_audit_school ON public.rbac_audit_log (school_id)"}
    with pytest.raises(RuntimeError, match="school/time index incompatible"):
        apply_rbac_audit_log(FakeConnection(indexes=indexes))


def test_apply_rejects_missing_indexes():
    with pytest.raises(RuntimeError, match="indexes incompatible"):
        apply_rbac_audit_log(FakeConnection(indexes=[]))


def test_apply_rejects_missing_append_only_trigger():
    with pytest.raises(RuntimeError, match="append-only triggers incompatible"):
        apply_rbac_audit_log(FakeConnection(triggers=[]))
