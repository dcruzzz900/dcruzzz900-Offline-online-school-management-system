import pytest

from postgres_migration_143_role_assignment_audit import (
    MIGRATION_NAME, MIGRATION_SOURCE, MIGRATION_VERSION,
    apply_role_assignment_audit, migration,
)
from postgres_migration_registry import POSTGRES_MIGRATIONS


class Result:
    def __init__(self, rows): self.rows = rows
    def fetchall(self): return self.rows


class FakeConnection:
    def __init__(self, columns=None, constraints=None, indexes=None, triggers=None):
        expected = {
            "id": ("bigint", True), "assignment_id": ("bigint", False),
            "user_id": ("bigint", True), "school_id": ("integer", True),
            "actor_user_id": ("bigint", False), "actor_name": ("text", False),
            "action": ("text", True), "previous_role": ("text", False),
            "new_role": ("text", False), "previous_scope": ("text", False),
            "new_scope": ("text", False), "approval_status": ("text", False),
            "reason": ("text", False), "created_at": ("text", False),
        }
        self.columns = columns if columns is not None else [
            {"column_name": n, "data_type": t, "is_nullable": "NO" if required else "YES"}
            for n, (t, required) in expected.items()
        ]
        self.constraints = constraints if constraints is not None else [
            {"conname": "role_assignment_audit_pkey", "contype": "p"}
        ]
        self.indexes = indexes if indexes is not None else [
            {"indexname": "role_assignment_audit_pkey", "indexdef": "CREATE UNIQUE INDEX role_assignment_audit_pkey ON public.role_assignment_audit USING btree (id)"},
            {"indexname": "idx_role_assignment_audit_school", "indexdef": "CREATE INDEX idx_role_assignment_audit_school ON public.role_assignment_audit USING btree (school_id)"},
        ]
        self.triggers = triggers if triggers is not None else [
            {"trigger_name": "trg_role_assignment_audit_no_update"},
            {"trigger_name": "trg_role_assignment_audit_no_delete"},
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
    assert MIGRATION_VERSION == 143
    assert MIGRATION_NAME == "create_role_assignment_audit"
    assert [item.version for item in POSTGRES_MIGRATIONS] == list(range(100, 188))
    assert next(item for item in POSTGRES_MIGRATIONS if item.version == 143).name == MIGRATION_NAME
    assert migration().version == 143
    assert "action TEXT NOT NULL" in MIGRATION_SOURCE


def test_apply_creates_table_index_and_append_only_triggers():
    conn = FakeConnection()
    apply_role_assignment_audit(conn)
    assert any("CREATE TABLE IF NOT EXISTS role_assignment_audit" in s for s in conn.statements)
    assert any("idx_role_assignment_audit_school" in s for s in conn.statements)
    assert any("trg_role_assignment_audit_no_update" in s for s in conn.statements)
    assert any("trg_role_assignment_audit_no_delete" in s for s in conn.statements)


def test_apply_rejects_wrong_columns():
    with pytest.raises(RuntimeError, match="columns incompatible"):
        apply_role_assignment_audit(FakeConnection(columns=[]))


def test_apply_rejects_unexpected_constraints():
    with pytest.raises(RuntimeError, match="constraints incompatible"):
        apply_role_assignment_audit(FakeConnection(constraints=[]))


def test_apply_rejects_wrong_index_definition():
    indexes = FakeConnection().indexes.copy()
    indexes[1] = {**indexes[1], "indexdef": "CREATE INDEX idx_role_assignment_audit_school ON public.role_assignment_audit (school_id, action)"}
    with pytest.raises(RuntimeError, match="indexes incompatible"):
        apply_role_assignment_audit(FakeConnection(indexes=indexes))


def test_apply_rejects_missing_indexes():
    with pytest.raises(RuntimeError, match="indexes incompatible"):
        apply_role_assignment_audit(FakeConnection(indexes=[]))


def test_apply_rejects_missing_append_only_trigger():
    with pytest.raises(RuntimeError, match="append-only triggers incompatible"):
        apply_role_assignment_audit(FakeConnection(triggers=[]))
