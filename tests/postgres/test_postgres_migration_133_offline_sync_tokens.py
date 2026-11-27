import pytest

from postgres_migration_133_offline_sync_tokens import (
    MIGRATION_NAME, MIGRATION_SOURCE, MIGRATION_VERSION,
    apply_offline_sync_tokens, migration,
)
from postgres_migration_registry import POSTGRES_MIGRATIONS


class Result:
    def __init__(self, rows): self.rows = rows
    def fetchall(self): return self.rows


class FakeConnection:
    def __init__(self, columns=None, constraints=None, indexes=None, fks=None, triggers=None):
        types = {
            "token": ("text", True), "entity_type": ("text", True),
            "entity_id": ("bigint", True), "created_at": ("text", False),
        }
        self.columns = columns if columns is not None else [
            {"column_name": n, "data_type": t, "is_nullable": "NO" if req else "YES"}
            for n, (t, req) in types.items()
        ]
        self.constraints = constraints if constraints is not None else [
            {"constraint_name": "offline_sync_tokens_pkey", "constraint_type": "PRIMARY KEY"}
        ]
        self.indexes = indexes if indexes is not None else [
            {"indexname": "offline_sync_tokens_pkey", "indexdef": "CREATE UNIQUE INDEX offline_sync_tokens_pkey ON public.offline_sync_tokens USING btree (token)"}
        ]
        self.fks = fks if fks is not None else []
        self.triggers = triggers if triggers is not None else []
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        if "information_schema.columns" in sql: return Result(self.columns)
        if "information_schema.table_constraints" in sql and "FOREIGN KEY" in sql: return Result(self.fks)
        if "information_schema.table_constraints" in sql: return Result(self.constraints)
        if "FROM pg_indexes" in sql: return Result(self.indexes)
        if "information_schema.triggers" in sql: return Result(self.triggers)
        return Result([])


def test_migration_registered_in_order():
    assert MIGRATION_VERSION == 133
    assert MIGRATION_NAME == "create_offline_sync_tokens"
    assert [item.version for item in POSTGRES_MIGRATIONS] == list(range(100, 188))
    assert next(item for item in POSTGRES_MIGRATIONS if item.version == 133).name == MIGRATION_NAME
    assert migration().version == 133


def test_ddl_preserves_source_columns_and_does_not_add_relationships():
    sql = MIGRATION_SOURCE.lower()
    for fragment in (
        "token text primary key", "entity_type text not null", "entity_id bigint not null",
        "created_at text default current_timestamp",
    ):
        assert fragment in sql
    assert "references " not in sql
    assert "create trigger" not in sql


def test_apply_executes_and_validates_migration():
    conn = FakeConnection()
    apply_offline_sync_tokens(conn)
    assert any("CREATE TABLE IF NOT EXISTS offline_sync_tokens" in sql for sql, _ in conn.calls)


def test_apply_rejects_wrong_columns():
    with pytest.raises(RuntimeError, match="columns incompatible"):
        apply_offline_sync_tokens(FakeConnection(columns=[]))


def test_apply_rejects_unexpected_foreign_keys():
    with pytest.raises(RuntimeError, match="must not have foreign keys"):
        apply_offline_sync_tokens(FakeConnection(fks=[{"constraint_name": "unexpected_fk"}]))


def test_apply_rejects_unexpected_indexes():
    with pytest.raises(RuntimeError, match="indexes incompatible"):
        apply_offline_sync_tokens(FakeConnection(indexes=[]))


def test_apply_rejects_unexpected_triggers():
    with pytest.raises(RuntimeError, match="must not have triggers"):
        apply_offline_sync_tokens(FakeConnection(triggers=[{"trigger_name": "unexpected_trigger"}]))
