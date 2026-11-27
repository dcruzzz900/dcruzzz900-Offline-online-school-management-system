import pytest

from postgres_migration_132_device_credentials import (
    MIGRATION_NAME, MIGRATION_SOURCE, MIGRATION_VERSION,
    apply_device_credentials, migration,
)
from postgres_migration_registry import POSTGRES_MIGRATIONS


class Result:
    def __init__(self, rows): self.rows = rows
    def fetchall(self): return self.rows
    def fetchone(self): return self.rows[0] if self.rows else None


class FakeConnection:
    def __init__(self, columns=None, fks=None, constraints=None, indexes=None, triggers=None, bad_dependency=None):
        types = {
            "id": ("bigint", True), "school_id": ("integer", True),
            "tenant_id": ("text", False), "user_id": ("integer", True),
            "device_id": ("text", True), "device_label": ("text", False),
            "secret_hash": ("text", True), "role_snapshot": ("text", True),
            "position_snapshot": ("text", False), "issued_at": ("text", False),
            "last_verified_at": ("text", False), "expires_at": ("text", True),
            "revoked": ("bigint", False), "revoked_reason": ("text", False),
        }
        self.columns = columns if columns is not None else [
            {"column_name": n, "data_type": t, "is_nullable": "NO" if req else "YES"}
            for n, (t, req) in types.items()
        ]
        self.fks = fks if fks is not None else [
            {"column_name": "school_id", "foreign_table_name": "schools", "foreign_column_name": "id"},
            {"column_name": "user_id", "foreign_table_name": "users", "foreign_column_name": "id"},
        ]
        self.constraints = constraints if constraints is not None else [
            {"constraint_name": "device_credentials_pkey", "constraint_type": "PRIMARY KEY"},
            {"constraint_name": "uq_device_credentials_device_id", "constraint_type": "UNIQUE"},
            {"constraint_name": "fk_device_credentials_school", "constraint_type": "FOREIGN KEY"},
            {"constraint_name": "fk_device_credentials_user", "constraint_type": "FOREIGN KEY"},
        ]
        self.indexes = indexes if indexes is not None else [
            {"indexname": "device_credentials_pkey", "indexdef": "CREATE UNIQUE INDEX device_credentials_pkey ON public.device_credentials USING btree (id)"},
            {"indexname": "uq_device_credentials_device_id", "indexdef": "CREATE UNIQUE INDEX uq_device_credentials_device_id ON public.device_credentials USING btree (device_id)"},
            {"indexname": "idx_device_credentials_tenant", "indexdef": "CREATE INDEX idx_device_credentials_tenant ON public.device_credentials USING btree (tenant_id)"},
            {"indexname": "idx_device_credentials_school", "indexdef": "CREATE INDEX idx_device_credentials_school ON public.device_credentials USING btree (school_id)"},
            {"indexname": "idx_device_credentials_user", "indexdef": "CREATE INDEX idx_device_credentials_user ON public.device_credentials USING btree (user_id)"},
        ]
        self.triggers = triggers if triggers is not None else [{"trigger_name": "trg_device_credentials_tenant_stamp"}]
        self.bad_dependency = bad_dependency
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        if "information_schema.columns" in sql and "column_name = ?" in sql:
            table = params[0]
            typ = "bigint" if self.bad_dependency == table else "integer"
            return Result([{"column_name": "id", "data_type": typ}])
        if "information_schema.columns" in sql: return Result(self.columns)
        if "information_schema.key_column_usage" in sql: return Result(self.fks)
        if "information_schema.table_constraints" in sql: return Result(self.constraints)
        if "FROM pg_indexes" in sql: return Result(self.indexes)
        if "information_schema.triggers" in sql: return Result(self.triggers)
        return Result([])


def test_migration_registered_in_order():
    assert MIGRATION_VERSION == 132
    assert MIGRATION_NAME == "create_device_credentials"
    assert [item.version for item in POSTGRES_MIGRATIONS] == list(range(100, 188))
    assert next(item for item in POSTGRES_MIGRATIONS if item.version == 132).name == MIGRATION_NAME
    assert migration().version == 132


def test_ddl_preserves_columns_relationships_indexes_and_tenant_trigger():
    sql = MIGRATION_SOURCE.lower()
    for fragment in (
        "school_id integer not null", "user_id integer not null", "tenant_id text",
        "secret_hash text not null", "issued_at text default current_timestamp",
        "revoked bigint default 0", "unique (device_id)",
        "foreign key (school_id) references schools(id)",
        "foreign key (user_id) references users(id)",
        "on device_credentials (tenant_id)", "on device_credentials (school_id)",
        "on device_credentials (user_id)", "trg_device_credentials_tenant_stamp",
        "new.tenant_id is null or new.tenant_id = ''",
    ):
        assert fragment in sql


def test_apply_executes_and_validates_migration():
    conn = FakeConnection()
    apply_device_credentials(conn)
    assert any("CREATE TABLE IF NOT EXISTS device_credentials" in sql for sql, _ in conn.calls)
    assert any("CREATE TRIGGER trg_device_credentials_tenant_stamp" in sql for sql, _ in conn.calls)


def test_apply_rejects_wrong_dependency_key_type():
    with pytest.raises(RuntimeError, match="users.id INTEGER"):
        apply_device_credentials(FakeConnection(bad_dependency="users"))


def test_apply_rejects_missing_foreign_key():
    with pytest.raises(RuntimeError, match="foreign keys incompatible"):
        apply_device_credentials(FakeConnection(fks=[{"column_name": "school_id", "foreign_table_name": "schools", "foreign_column_name": "id"}]))


def test_apply_rejects_incompatible_indexes():
    with pytest.raises(RuntimeError, match="indexes incompatible"):
        apply_device_credentials(FakeConnection(indexes=[]))


def test_apply_rejects_missing_tenant_trigger():
    with pytest.raises(RuntimeError, match="triggers incompatible"):
        apply_device_credentials(FakeConnection(triggers=[]))
