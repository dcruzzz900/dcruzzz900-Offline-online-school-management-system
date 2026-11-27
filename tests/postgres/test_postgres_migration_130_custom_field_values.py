import pytest

from postgres_migration_130_custom_field_values import (
    MIGRATION_NAME, MIGRATION_SOURCE, MIGRATION_VERSION,
    apply_custom_field_values, migration,
)
from postgres_migration_registry import POSTGRES_MIGRATIONS


class Result:
    def __init__(self, rows): self.rows = rows
    def fetchall(self): return self.rows


class FakeConnection:
    def __init__(self, columns=None, indexes=None, constraints=None, triggers=None):
        types = {
            "id": ("bigint", True), "field_id": ("bigint", True),
            "school_id": ("bigint", True), "tenant_id": ("text", True),
            "entity_type": ("text", True), "entity_id": ("bigint", True),
            "value": ("text", False), "unique_value": ("text", False),
            "updated_by": ("bigint", False), "updated_at": ("text", False),
        }
        self.columns = columns if columns is not None else [
            {"column_name": n, "data_type": t, "is_nullable": "NO" if req else "YES"}
            for n, (t, req) in types.items()
        ]
        self.indexes = indexes if indexes is not None else [
            {"indexname": "custom_field_values_pkey", "indexdef": "CREATE UNIQUE INDEX custom_field_values_pkey ON public.custom_field_values USING btree (id)"},
            {"indexname": "uq_custom_field_values_field_entity", "indexdef": "CREATE UNIQUE INDEX uq_custom_field_values_field_entity ON public.custom_field_values USING btree (field_id, entity_id)"},
            {"indexname": "idx_custom_values_entity", "indexdef": "CREATE INDEX idx_custom_values_entity ON public.custom_field_values USING btree (school_id, entity_type, entity_id)"},
            {"indexname": "ux_custom_values_unique", "indexdef": "CREATE UNIQUE INDEX ux_custom_values_unique ON public.custom_field_values USING btree (field_id, unique_value) WHERE (unique_value IS NOT NULL)"},
        ]
        self.constraints = constraints if constraints is not None else [
            {"constraint_name": "ck_custom_field_values_entity_type", "constraint_type": "CHECK"},
            {"constraint_name": "uq_custom_field_values_field_entity", "constraint_type": "UNIQUE"},
            {"constraint_name": "custom_field_values_pkey", "constraint_type": "PRIMARY KEY"},
        ]
        self.triggers = triggers if triggers is not None else []
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        if "information_schema.columns" in sql: return Result(self.columns)
        if "information_schema.table_constraints" in sql: return Result(self.constraints)
        if "FROM pg_indexes" in sql: return Result(self.indexes)
        if "information_schema.triggers" in sql: return Result(self.triggers)
        return Result([])


def test_migration_registered_in_order():
    assert MIGRATION_VERSION == 130
    assert MIGRATION_NAME == "create_custom_field_values"
    assert [item.version for item in POSTGRES_MIGRATIONS] == list(range(100, 188))
    assert next(item for item in POSTGRES_MIGRATIONS if item.version == 130).name == MIGRATION_NAME
    assert migration().version == 130


def test_ddl_preserves_columns_constraints_and_indexes():
    sql = MIGRATION_SOURCE.lower()
    for fragment in (
        "field_id bigint not null", "tenant_id text not null",
        "check (entity_type in ('student', 'staff'))",
        "unique (field_id, entity_id)",
        "on custom_field_values (school_id, entity_type, entity_id)",
        "on custom_field_values (field_id, unique_value) where unique_value is not null",
        "updated_at text default current_timestamp",
    ):
        assert fragment in sql


def test_apply_executes_and_validates_migration():
    conn = FakeConnection()
    apply_custom_field_values(conn)
    assert any("CREATE TABLE IF NOT EXISTS custom_field_values" in sql for sql, _ in conn.calls)
    assert any("ux_custom_values_unique" in sql for sql, _ in conn.calls)


def test_apply_rejects_missing_column():
    columns = [r for r in FakeConnection().columns if r["column_name"] != "tenant_id"]
    with pytest.raises(RuntimeError, match="columns incompatible"):
        apply_custom_field_values(FakeConnection(columns=columns))


def test_apply_rejects_missing_check_constraint():
    constraints = [r for r in FakeConnection().constraints if r["constraint_name"] != "ck_custom_field_values_entity_type"]
    with pytest.raises(RuntimeError, match="entity_type CHECK"):
        apply_custom_field_values(FakeConnection(constraints=constraints))


def test_apply_rejects_unexpected_foreign_key():
    constraints = FakeConnection().constraints + [{"constraint_name": "unexpected_fk", "constraint_type": "FOREIGN KEY"}]
    with pytest.raises(RuntimeError, match="unexpected foreign keys"):
        apply_custom_field_values(FakeConnection(constraints=constraints))


def test_apply_rejects_incompatible_indexes():
    indexes = [r for r in FakeConnection().indexes if r["indexname"] != "ux_custom_values_unique"]
    with pytest.raises(RuntimeError, match="indexes incompatible"):
        apply_custom_field_values(FakeConnection(indexes=indexes))


def test_apply_rejects_incompatible_partial_unique_index():
    indexes = list(FakeConnection().indexes)
    indexes[-1] = {"indexname": "ux_custom_values_unique", "indexdef": "CREATE UNIQUE INDEX ux_custom_values_unique ON custom_field_values (field_id, unique_value)"}
    with pytest.raises(RuntimeError, match="conditional unique index"):
        apply_custom_field_values(FakeConnection(indexes=indexes))


def test_apply_rejects_unexpected_triggers():
    with pytest.raises(RuntimeError, match="unexpected triggers"):
        apply_custom_field_values(FakeConnection(triggers=[{"trigger_name": "unexpected"}]))
