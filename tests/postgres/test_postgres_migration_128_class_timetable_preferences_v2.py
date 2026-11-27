import pytest

from postgres_migration_128_class_timetable_preferences_v2 import (
    MIGRATION_NAME, MIGRATION_SOURCE, MIGRATION_VERSION,
    apply_class_timetable_preferences_v2, migration,
)
from postgres_migration_registry import POSTGRES_MIGRATIONS


class Result:
    def __init__(self, rows): self.rows = rows
    def fetchall(self): return self.rows
    def fetchone(self): return self.rows[0] if self.rows else None


class FakeConnection:
    def __init__(self, columns=None, indexes=None, fks=None, triggers=None, bad_dependency=None):
        types = {
            "id": ("bigint", True), "tenant_id": ("text", True),
            "school_id": ("integer", True), "class_id": ("integer", True),
            "arm_id": ("bigint", False), "subject_id": ("bigint", False),
            "preferred_days": ("text", False), "preferred_slots": ("text", False),
            "avoid_days": ("text", False), "avoid_slots": ("text", False),
            "max_subject_periods_per_day": ("bigint", False), "status": ("text", True),
            "client_uuid": ("text", False), "updated_at": ("text", False),
            "is_deleted": ("bigint", False),
        }
        self.columns = columns if columns is not None else [
            {"column_name": n, "data_type": t, "is_nullable": "NO" if nullable else "YES"}
            for n, (t, nullable) in types.items()
        ]
        self.indexes = indexes if indexes is not None else [
            {"indexname": "class_timetable_preferences_v2_pkey", "indexdef": "CREATE UNIQUE INDEX class_timetable_preferences_v2_pkey ON public.class_timetable_preferences_v2 USING btree (id)"},
            {"indexname": "idx_class_timetable_preferences_v2_client_uuid", "indexdef": "CREATE UNIQUE INDEX idx_class_timetable_preferences_v2_client_uuid ON public.class_timetable_preferences_v2 USING btree (client_uuid) WHERE (client_uuid IS NOT NULL)"},
        ]
        self.fks = fks if fks is not None else [
            {"column_name": "school_id", "foreign_table_name": "schools", "foreign_column_name": "id"},
            {"column_name": "class_id", "foreign_table_name": "classes", "foreign_column_name": "id"},
        ]
        self.triggers = triggers if triggers is not None else [
            {"trigger_name": "trg_class_timetable_preferences_v2_sync_defaults"},
            {"trigger_name": "trg_class_timetable_preferences_v2_sync_touch"},
        ]
        self.bad_dependency = bad_dependency
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        if "information_schema.columns" in sql and "column_name = ?" in sql:
            if params[0] == self.bad_dependency:
                return Result([])
            return Result([{"column_name": "id", "data_type": "integer"}])
        if "information_schema.columns" in sql:
            return Result(self.columns)
        if "information_schema.table_constraints" in sql and "FOREIGN KEY" in sql:
            return Result(self.fks)
        if "FROM pg_indexes" in sql:
            return Result(self.indexes)
        if "information_schema.triggers" in sql:
            return Result(self.triggers)
        return Result([])


def test_migration_registered_in_order():
    assert MIGRATION_VERSION == 128
    assert MIGRATION_NAME == "create_class_timetable_preferences_v2"
    assert [item.version for item in POSTGRES_MIGRATIONS] == list(range(100, 188))
    assert next(item for item in POSTGRES_MIGRATIONS if item.version == 128).name == MIGRATION_NAME
    assert migration().version == 128


def test_ddl_preserves_columns_defaults_foreign_keys_and_sync_triggers():
    sql = MIGRATION_SOURCE.lower()
    for fragment in (
        "tenant_id text not null", "school_id integer not null", "class_id integer not null",
        "status text not null default 'active'", "is_deleted bigint default 0",
        "references schools(id)", "references classes(id)",
        "where client_uuid is not null", "before insert", "before update",
    ):
        assert fragment in sql
    assert "preferred_days text" in sql and "preferred_slots text" in sql


def test_apply_executes_and_validates_migration():
    conn = FakeConnection()
    apply_class_timetable_preferences_v2(conn)
    assert any("CREATE TABLE IF NOT EXISTS class_timetable_preferences_v2" in sql for sql, _ in conn.calls)
    assert any("CREATE TRIGGER trg_class_timetable_preferences_v2_sync_defaults" in sql for sql, _ in conn.calls)
    assert any("CREATE TRIGGER trg_class_timetable_preferences_v2_sync_touch" in sql for sql, _ in conn.calls)


def test_apply_rejects_missing_column():
    columns = [r for r in FakeConnection().columns if r["column_name"] != "tenant_id"]
    with pytest.raises(RuntimeError, match="columns incompatible"):
        apply_class_timetable_preferences_v2(FakeConnection(columns=columns))


@pytest.mark.parametrize("dependency", ["schools", "classes"])
def test_apply_rejects_missing_or_wrong_dependency(dependency):
    with pytest.raises(RuntimeError, match=f"requires {dependency}.id INTEGER"):
        apply_class_timetable_preferences_v2(FakeConnection(bad_dependency=dependency))


def test_apply_rejects_incompatible_foreign_keys():
    with pytest.raises(RuntimeError, match="foreign keys incompatible"):
        apply_class_timetable_preferences_v2(FakeConnection(fks=[]))


def test_apply_rejects_incompatible_indexes():
    indexes = [r for r in FakeConnection().indexes if r["indexname"] != "idx_class_timetable_preferences_v2_client_uuid"]
    with pytest.raises(RuntimeError, match="indexes incompatible"):
        apply_class_timetable_preferences_v2(FakeConnection(indexes=indexes))


def test_apply_rejects_incompatible_triggers():
    with pytest.raises(RuntimeError, match="triggers incompatible"):
        apply_class_timetable_preferences_v2(FakeConnection(triggers=[]))
