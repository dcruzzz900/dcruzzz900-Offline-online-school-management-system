import pytest

from postgres_migration_125_class_login_codes import (
    MIGRATION_NAME, MIGRATION_SOURCE, MIGRATION_VERSION,
    apply_class_login_codes, migration,
)
from postgres_migration_registry import POSTGRES_MIGRATIONS


class Result:
    def __init__(self, rows): self.rows = rows
    def fetchall(self): return self.rows


class FakeConnection:
    def __init__(self, columns=None, indexes=None, fks=None, checks=None, triggers=None):
        types = {
            "id": "bigint", "school_id": "bigint", "tenant_id": "text",
            "class_id": "bigint", "code": "text", "status": "text",
            "expires_at": "text", "created_by": "bigint", "created_by_name": "text",
            "created_at": "text", "ended_at": "text", "ended_by": "bigint",
            "ended_by_name": "text", "end_reason": "text", "use_count": "bigint",
        }
        nullable = {"expires_at", "created_by", "created_by_name", "created_at", "ended_at", "ended_by", "ended_by_name", "end_reason"}
        self.columns = columns if columns is not None else [
            {"column_name": n, "data_type": t, "is_nullable": "YES" if n in nullable else "NO"}
            for n, t in types.items()
        ]
        self.indexes = indexes if indexes is not None else [
            {"indexname": "class_login_codes_pkey", "indexdef": "CREATE UNIQUE INDEX class_login_codes_pkey ON public.class_login_codes USING btree (id)"},
            {"indexname": "idx_class_login_codes_school", "indexdef": "CREATE INDEX idx_class_login_codes_school ON public.class_login_codes USING btree (school_id, class_id)"},
            {"indexname": "ux_class_login_codes_code", "indexdef": "CREATE UNIQUE INDEX ux_class_login_codes_code ON public.class_login_codes USING btree (code)"},
            {"indexname": "ux_class_login_codes_one_active", "indexdef": "CREATE UNIQUE INDEX ux_class_login_codes_one_active ON public.class_login_codes USING btree (class_id) WHERE (status = 'active'::text)"},
        ]
        self.fks = fks if fks is not None else []
        self.checks = checks if checks is not None else [{"check_clause": "status = ANY (ARRAY['active', 'revoked', 'rotated', 'expired'])"}]
        self.triggers = triggers if triggers is not None else []
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        if "information_schema.columns" in sql: return Result(self.columns)
        if "information_schema.table_constraints" in sql and "FOREIGN KEY" in sql: return Result(self.fks)
        if "FROM pg_indexes" in sql: return Result(self.indexes)
        if "information_schema.check_constraints" in sql: return Result(self.checks)
        if "information_schema.triggers" in sql: return Result(self.triggers)
        return Result([])


def test_class_login_codes_registered_in_order():
    assert MIGRATION_VERSION == 125
    assert MIGRATION_NAME == "create_class_login_codes"
    assert [item.version for item in POSTGRES_MIGRATIONS] == list(range(100, 143))
    assert next(item for item in POSTGRES_MIGRATIONS if item.version == 125).name == MIGRATION_NAME
    assert migration().version == 125


def test_ddl_preserves_columns_status_check_and_indexes():
    sql = MIGRATION_SOURCE.lower()
    for fragment in (
        "tenant_id text not null", "status text not null default 'active'",
        "check (status in ('active', 'revoked', 'rotated', 'expired'))",
        "created_at text default current_timestamp", "use_count bigint not null default 0",
        "idx_class_login_codes_school on class_login_codes (school_id, class_id)",
        "ux_class_login_codes_code on class_login_codes (code)",
        "ux_class_login_codes_one_active on class_login_codes (class_id) where status = 'active'",
    ):
        assert fragment in sql


def test_apply_validates_and_executes_migration():
    conn = FakeConnection()
    apply_class_login_codes(conn)
    assert any("CREATE TABLE IF NOT EXISTS class_login_codes" in sql for sql, _ in conn.calls)


def test_apply_rejects_missing_column():
    columns = [r for r in FakeConnection().columns if r["column_name"] != "tenant_id"]
    with pytest.raises(RuntimeError, match="missing columns"):
        apply_class_login_codes(FakeConnection(columns=columns))


def test_apply_rejects_incompatible_column_type():
    columns = [dict(r) for r in FakeConnection().columns]
    next(r for r in columns if r["column_name"] == "class_id")["data_type"] = "integer"
    with pytest.raises(RuntimeError, match="incompatible columns"):
        apply_class_login_codes(FakeConnection(columns=columns))


def test_apply_rejects_unexpected_foreign_key():
    with pytest.raises(RuntimeError, match="unexpected foreign keys"):
        apply_class_login_codes(FakeConnection(fks=[{"constraint_name": "unexpected_fk"}]))


def test_apply_rejects_missing_or_incompatible_indexes():
    indexes = [r for r in FakeConnection().indexes if r["indexname"] != "ux_class_login_codes_one_active"]
    with pytest.raises(RuntimeError, match="indexes"):
        apply_class_login_codes(FakeConnection(indexes=indexes))


def test_apply_rejects_incompatible_status_check():
    with pytest.raises(RuntimeError, match="status CHECK"):
        apply_class_login_codes(FakeConnection(checks=[{"check_clause": "status IN ('active')"}]))


def test_apply_rejects_unexpected_trigger():
    with pytest.raises(RuntimeError, match="unexpected triggers"):
        apply_class_login_codes(FakeConnection(triggers=[{"trigger_name": "unexpected_trigger"}]))
