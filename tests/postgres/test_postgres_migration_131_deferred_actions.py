import pytest

from postgres_migration_131_deferred_actions import (
    MIGRATION_NAME, MIGRATION_SOURCE, MIGRATION_VERSION,
    apply_deferred_actions, migration,
)
from postgres_migration_registry import POSTGRES_MIGRATIONS


class Result:
    def __init__(self, rows): self.rows = rows
    def fetchall(self): return self.rows


class FakeConnection:
    def __init__(self, columns=None, constraints=None, fks=None, indexes=None, triggers=None):
        types = {
            "id": ("bigint", True), "school_id": ("integer", True),
            "device_id": ("text", False), "user_id": ("bigint", False),
            "client_uuid": ("text", True), "action_type": ("text", True),
            "payload": ("text", True), "status": ("text", True),
            "result_message": ("text", False), "created_at": ("text", False),
            "processed_at": ("text", False), "tenant_id": ("text", False),
        }
        self.columns = columns if columns is not None else [
            {"column_name": n, "data_type": t, "is_nullable": "NO" if req else "YES"}
            for n, (t, req) in types.items()
        ]
        self.constraints = constraints if constraints is not None else [
            {"constraint_name": "deferred_actions_pkey", "constraint_type": "PRIMARY KEY"},
            {"constraint_name": "uq_deferred_actions_client_uuid", "constraint_type": "UNIQUE"},
            {"constraint_name": "fk_deferred_actions_school", "constraint_type": "FOREIGN KEY"},
        ]
        self.fks = fks if fks is not None else [
            {"column_name": "school_id", "foreign_table_name": "schools", "foreign_column_name": "id"}
        ]
        self.indexes = indexes if indexes is not None else [
            {"indexname": "deferred_actions_pkey", "indexdef": "CREATE UNIQUE INDEX deferred_actions_pkey ON public.deferred_actions USING btree (id)"},
            {"indexname": "uq_deferred_actions_client_uuid", "indexdef": "CREATE UNIQUE INDEX uq_deferred_actions_client_uuid ON public.deferred_actions USING btree (client_uuid)"},
            {"indexname": "idx_deferred_actions_school", "indexdef": "CREATE INDEX idx_deferred_actions_school ON public.deferred_actions USING btree (school_id)"},
        ]
        self.triggers = triggers if triggers is not None else []
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        if "information_schema.columns" in sql: return Result(self.columns)
        if "information_schema.key_column_usage" in sql: return Result(self.fks)
        if "information_schema.table_constraints" in sql: return Result(self.constraints)
        if "FROM pg_indexes" in sql: return Result(self.indexes)
        if "information_schema.triggers" in sql: return Result(self.triggers)
        return Result([])


def test_migration_registered_in_order():
    assert MIGRATION_VERSION == 131
    assert MIGRATION_NAME == "create_deferred_actions"
    assert [item.version for item in POSTGRES_MIGRATIONS] == list(range(100, 188))
    assert next(item for item in POSTGRES_MIGRATIONS if item.version == 131).name == MIGRATION_NAME
    assert migration().version == 131


def test_ddl_preserves_source_columns_relationship_and_indexes():
    sql = MIGRATION_SOURCE.lower()
    for fragment in (
        "school_id integer not null", "user_id bigint", "client_uuid text not null",
        "status text not null default 'pending'", "created_at text default current_timestamp",
        "unique (client_uuid)", "foreign key (school_id) references schools(id)",
        "on deferred_actions (school_id)",
    ):
        assert fragment in sql


def test_apply_executes_and_validates_migration():
    conn = FakeConnection()
    apply_deferred_actions(conn)
    assert any("CREATE TABLE IF NOT EXISTS deferred_actions" in sql for sql, _ in conn.calls)
    assert any("idx_deferred_actions_school" in sql for sql, _ in conn.calls)


def test_apply_rejects_missing_column():
    columns = [r for r in FakeConnection().columns if r["column_name"] != "tenant_id"]
    with pytest.raises(RuntimeError, match="columns incompatible"):
        apply_deferred_actions(FakeConnection(columns=columns))


def test_apply_rejects_wrong_foreign_key():
    with pytest.raises(RuntimeError, match="foreign keys incompatible"):
        apply_deferred_actions(FakeConnection(fks=[{"column_name": "school_id", "foreign_table_name": "users", "foreign_column_name": "id"}]))


def test_apply_rejects_missing_unique_constraint():
    constraints = [r for r in FakeConnection().constraints if r["constraint_name"] != "uq_deferred_actions_client_uuid"]
    with pytest.raises(RuntimeError, match="constraints incompatible"):
        apply_deferred_actions(FakeConnection(constraints=constraints))


def test_apply_rejects_incompatible_indexes():
    indexes = [r for r in FakeConnection().indexes if r["indexname"] != "idx_deferred_actions_school"]
    with pytest.raises(RuntimeError, match="indexes incompatible"):
        apply_deferred_actions(FakeConnection(indexes=indexes))


def test_apply_rejects_unexpected_triggers():
    with pytest.raises(RuntimeError, match="unexpected triggers"):
        apply_deferred_actions(FakeConnection(triggers=[{"trigger_name": "unexpected"}]))
