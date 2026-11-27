import pytest

from postgres_migration_129_custom_fields import (
    MIGRATION_NAME, MIGRATION_SOURCE, MIGRATION_VERSION,
    apply_custom_fields, migration,
)
from postgres_migration_registry import POSTGRES_MIGRATIONS


class Result:
    def __init__(self, rows): self.rows = rows
    def fetchall(self): return self.rows
    def fetchone(self): return self.rows[0] if self.rows else None


class FakeConnection:
    def __init__(self, columns=None, indexes=None, constraints=None, triggers=None):
        types = {
            "id": ("bigint", True), "school_id": ("integer", True),
            "tenant_id": ("text", True), "applies_to": ("text", True),
            "field_key": ("text", True), "label": ("text", True),
            "description": ("text", False), "field_type": ("text", True),
            "is_required": ("bigint", True), "is_unique": ("bigint", True),
            "is_editable": ("bigint", True), "default_value": ("text", False),
            "is_active": ("bigint", True), "is_archived": ("bigint", True),
            "display_order": ("bigint", True), "created_by": ("bigint", False),
            "created_by_name": ("text", False), "updated_by": ("bigint", False),
            "updated_by_name": ("text", False), "created_at": ("text", False),
            "updated_at": ("text", False),
        }
        self.columns = columns if columns is not None else [
            {"column_name": name, "data_type": kind, "is_nullable": "NO" if required else "YES"}
            for name, (kind, required) in types.items()
        ]
        self.indexes = indexes if indexes is not None else [
            {"indexname": "custom_fields_pkey", "indexdef": "CREATE UNIQUE INDEX custom_fields_pkey ON public.custom_fields USING btree (id)"},
            {"indexname": "uq_custom_fields_school_applies_field_key", "indexdef": "CREATE UNIQUE INDEX uq_custom_fields_school_applies_field_key ON public.custom_fields USING btree (school_id, applies_to, field_key)"},
            {"indexname": "idx_custom_fields_scope", "indexdef": "CREATE INDEX idx_custom_fields_scope ON public.custom_fields USING btree (school_id, tenant_id, applies_to)"},
            {"indexname": "ux_custom_fields_label", "indexdef": "CREATE UNIQUE INDEX ux_custom_fields_label ON public.custom_fields USING btree (school_id, applies_to, lower(label)) WHERE (is_archived = 0)"},
        ]
        self.constraints = constraints if constraints is not None else [
            {"constraint_name": "ck_custom_fields_applies_to", "constraint_type": "CHECK"},
            {"constraint_name": "uq_custom_fields_school_applies_field_key", "constraint_type": "UNIQUE"},
            {"constraint_name": "custom_fields_pkey", "constraint_type": "PRIMARY KEY"},
        ]
        self.triggers = triggers if triggers is not None else []
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        if "information_schema.columns" in sql:
            return Result(self.columns)
        if "information_schema.table_constraints" in sql:
            return Result(self.constraints)
        if "FROM pg_indexes" in sql:
            return Result(self.indexes)
        if "information_schema.triggers" in sql:
            return Result(self.triggers)
        return Result([])


def test_migration_registered_in_order():
    assert MIGRATION_VERSION == 129
    assert MIGRATION_NAME == "create_custom_fields"
    assert [item.version for item in POSTGRES_MIGRATIONS] == list(range(100, 188))
    assert next(item for item in POSTGRES_MIGRATIONS if item.version == 129).name == MIGRATION_NAME
    assert migration().version == 129


def test_ddl_preserves_columns_constraints_and_indexes():
    sql = MIGRATION_SOURCE.lower()
    for fragment in (
        "school_id integer not null", "tenant_id text not null",
        "check (applies_to in ('student', 'staff'))",
        "default 0", "default 1", "unique (school_id, applies_to, field_key)",
        "on custom_fields (school_id, tenant_id, applies_to)",
        "lower(label)", "where is_archived = 0",
    ):
        assert fragment in sql


def test_apply_executes_and_validates_migration():
    conn = FakeConnection()
    apply_custom_fields(conn)
    assert any("CREATE TABLE IF NOT EXISTS custom_fields" in sql for sql, _ in conn.calls)
    assert any("ux_custom_fields_label" in sql for sql, _ in conn.calls)


def test_apply_rejects_missing_column():
    columns = [row for row in FakeConnection().columns if row["column_name"] != "tenant_id"]
    with pytest.raises(RuntimeError, match="columns incompatible"):
        apply_custom_fields(FakeConnection(columns=columns))


def test_apply_rejects_missing_check_constraint():
    constraints = [row for row in FakeConnection().constraints if row["constraint_name"] != "ck_custom_fields_applies_to"]
    with pytest.raises(RuntimeError, match="applies_to CHECK"):
        apply_custom_fields(FakeConnection(constraints=constraints))


def test_apply_rejects_unexpected_foreign_key():
    constraints = FakeConnection().constraints + [{"constraint_name": "unexpected_fk", "constraint_type": "FOREIGN KEY"}]
    with pytest.raises(RuntimeError, match="unexpected foreign keys"):
        apply_custom_fields(FakeConnection(constraints=constraints))


def test_apply_rejects_incompatible_indexes():
    indexes = [row for row in FakeConnection().indexes if row["indexname"] != "ux_custom_fields_label"]
    with pytest.raises(RuntimeError, match="indexes incompatible"):
        apply_custom_fields(FakeConnection(indexes=indexes))


def test_apply_rejects_incompatible_label_index():
    indexes = list(FakeConnection().indexes)
    indexes[-1] = {"indexname": "ux_custom_fields_label", "indexdef": "CREATE UNIQUE INDEX ux_custom_fields_label ON custom_fields (label)"}
    with pytest.raises(RuntimeError, match="case-insensitive label index"):
        apply_custom_fields(FakeConnection(indexes=indexes))


def test_apply_rejects_unexpected_triggers():
    with pytest.raises(RuntimeError, match="unexpected triggers"):
        apply_custom_fields(FakeConnection(triggers=[{"trigger_name": "unexpected_trigger"}]))
