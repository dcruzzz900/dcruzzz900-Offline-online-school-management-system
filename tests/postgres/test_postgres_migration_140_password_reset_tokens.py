import pytest

from postgres_migration_140_password_reset_tokens import (
    MIGRATION_NAME, MIGRATION_SOURCE, MIGRATION_VERSION,
    apply_password_reset_tokens, migration,
)
from postgres_migration_registry import POSTGRES_MIGRATIONS


class Result:
    def __init__(self, rows): self.rows = rows
    def fetchall(self): return self.rows
    def fetchone(self): return self.rows[0] if self.rows else None


class FakeConnection:
    def __init__(self, columns=None, constraints=None, indexes=None, fks=None, triggers=None):
        expected = {
            "id": ("bigint", True), "account_type": ("text", True),
            "account_id": ("bigint", True), "token_hash": ("text", True),
            "created_at": ("text", True), "expires_at": ("text", True),
            "used_at": ("text", False),
        }
        self.columns = columns if columns is not None else [
            {"column_name": n, "data_type": t, "is_nullable": "NO" if required else "YES"}
            for n, (t, required) in expected.items()
        ]
        self.constraints = constraints if constraints is not None else [
            {"conname": "password_reset_tokens_pkey", "contype": "p", "definition": "PRIMARY KEY (id)"},
            {"conname": "password_reset_tokens_account_type_check", "contype": "c", "definition": "CHECK ((account_type = ANY (ARRAY['staff'::text, 'parent'::text])))"},
            {"conname": "password_reset_tokens_token_hash_key", "contype": "u", "definition": "UNIQUE (token_hash)"},
        ]
        self.indexes = indexes if indexes is not None else [
            {"indexname": "password_reset_tokens_pkey", "indexdef": "CREATE UNIQUE INDEX password_reset_tokens_pkey ON public.password_reset_tokens USING btree (id)"},
            {"indexname": "password_reset_tokens_token_hash_key", "indexdef": "CREATE UNIQUE INDEX password_reset_tokens_token_hash_key ON public.password_reset_tokens USING btree (token_hash)"},
            {"indexname": "idx_password_reset_tokens_account", "indexdef": "CREATE INDEX idx_password_reset_tokens_account ON public.password_reset_tokens USING btree (account_type, account_id)"},
        ]
        self.fks = fks or []
        self.triggers = triggers or []
        self.statements = []

    def execute(self, sql, params=()):
        self.statements.append(sql)
        if "information_schema.columns" in sql: return Result(self.columns)
        if "FROM pg_constraint" in sql: return Result(self.constraints)
        if "constraint_type = 'FOREIGN KEY'" in sql: return Result(self.fks)
        if "FROM pg_indexes" in sql: return Result(self.indexes)
        if "information_schema.triggers" in sql: return Result(self.triggers)
        return Result([])


def test_registry_and_metadata():
    assert MIGRATION_VERSION == 140
    assert MIGRATION_NAME == "create_password_reset_tokens"
    assert [item.version for item in POSTGRES_MIGRATIONS] == list(range(100, 143))
    assert next(item for item in POSTGRES_MIGRATIONS if item.version == 140).name == MIGRATION_NAME
    assert migration().version == 140
    assert "account_type IN ('staff', 'parent')" in MIGRATION_SOURCE


def test_apply_creates_and_validates_table():
    conn = FakeConnection()
    apply_password_reset_tokens(conn)
    assert any("CREATE TABLE IF NOT EXISTS password_reset_tokens" in sql for sql in conn.statements)
    assert any("idx_password_reset_tokens_account" in sql for sql in conn.statements)


def test_apply_rejects_wrong_columns():
    with pytest.raises(RuntimeError, match="columns incompatible"):
        apply_password_reset_tokens(FakeConnection(columns=[]))


def test_apply_rejects_wrong_constraints():
    with pytest.raises(RuntimeError, match="constraints incompatible"):
        apply_password_reset_tokens(FakeConnection(constraints=[]))


def test_apply_rejects_missing_account_type_check_values():
    constraints = FakeConnection().constraints.copy()
    constraints[1] = {**constraints[1], "definition": "CHECK (account_type = 'staff')"}
    with pytest.raises(RuntimeError, match="CHECK constraint incompatible"):
        apply_password_reset_tokens(FakeConnection(constraints=constraints))


def test_apply_rejects_foreign_keys():
    with pytest.raises(RuntimeError, match="must not have foreign keys"):
        apply_password_reset_tokens(FakeConnection(fks=[{"constraint_name": "unexpected_fk"}]))


def test_apply_rejects_wrong_indexes():
    with pytest.raises(RuntimeError, match="indexes incompatible"):
        apply_password_reset_tokens(FakeConnection(indexes=[]))


def test_apply_rejects_wrong_account_lookup_index():
    indexes = FakeConnection().indexes.copy()
    indexes[2] = {**indexes[2], "indexdef": "CREATE INDEX idx_password_reset_tokens_account ON public.password_reset_tokens USING btree (account_id)"}
    with pytest.raises(RuntimeError, match="account lookup index incompatible"):
        apply_password_reset_tokens(FakeConnection(indexes=indexes))


def test_apply_rejects_triggers():
    with pytest.raises(RuntimeError, match="must not have triggers"):
        apply_password_reset_tokens(FakeConnection(triggers=[{"trigger_name": "unexpected"}]))
