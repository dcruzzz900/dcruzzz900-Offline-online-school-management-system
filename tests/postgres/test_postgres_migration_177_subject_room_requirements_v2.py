import pytest

from postgres_migration_177_subject_room_requirements_v2 import (
    MIGRATION_NAME, MIGRATION_SOURCE, MIGRATION_STATEMENTS, MIGRATION_VERSION,
    _EXPECTED_COLUMNS, apply_subject_room_requirements_v2, migration,
)
from postgres_migration_registry import POSTGRES_MIGRATIONS

UNIQUE_COLUMNS = ('tenant_id', 'school_id', 'subject_id', 'room_id')


class Result:
    def __init__(self, rows): self.rows = rows
    def fetchall(self): return self.rows
    def fetchone(self): return self.rows[0] if self.rows else None


class FakeConnection:
    def __init__(self, columns=None, fks=None, uniques=None, checks=None, indexes=None, triggers=None, parent_types=None):
        self.columns = columns if columns is not None else [
            {"column_name": n, "data_type": typ, "is_nullable": "NO" if req else "YES"}
            for n, (typ, req) in _EXPECTED_COLUMNS.items()
        ]
        self.fks = fks if fks is not None else [
            {"column_name": "school_id", "foreign_table_name": "schools", "foreign_column_name": "id"},
            {"column_name": "subject_id", "foreign_table_name": "subjects", "foreign_column_name": "id"},
            {"column_name": "room_id", "foreign_table_name": "timetable_rooms_v2", "foreign_column_name": "id"},
        ]
        self.uniques = uniques if uniques is not None else [
            {"constraint_name": "uq_subject_room_requirements_v2_subject_room", "column_name": c, "ordinal_position": i}
            for i, c in enumerate(UNIQUE_COLUMNS, 1)
        ]
        self.checks = checks if checks is not None else []
        self.indexes = indexes if indexes is not None else [
            {"indexname": "subject_room_requirements_v2_pkey", "indexdef": "CREATE UNIQUE INDEX subject_room_requirements_v2_pkey ON public.subject_room_requirements_v2 USING btree (id)"},
            {"indexname": "uq_subject_room_requirements_v2_subject_room", "indexdef": "CREATE UNIQUE INDEX uq_subject_room_requirements_v2_subject_room ON public.subject_room_requirements_v2 USING btree (tenant_id, school_id, subject_id, room_id)"},
            {"indexname": "idx_subject_room_requirements_v2_client_uuid", "indexdef": "CREATE UNIQUE INDEX idx_subject_room_requirements_v2_client_uuid ON public.subject_room_requirements_v2 USING btree (client_uuid) WHERE (client_uuid IS NOT NULL)"},
        ]
        self.triggers = triggers if triggers is not None else [
            {"trigger_name": "trg_subject_room_requirements_v2_sync_defaults"}, {"trigger_name": "trg_subject_room_requirements_v2_sync_touch"}]
        self.parent_types = {"schools": "integer", "subjects": "integer", "timetable_rooms_v2": "bigint"}
        self.parent_types.update(parent_types or {})
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        if "information_schema.columns" in sql and params and params[0] in self.parent_types:
            return Result([{"column_name": "id", "data_type": self.parent_types[params[0]]}])
        if "information_schema.columns" in sql: return Result(self.columns)
        if "constraint_type = 'FOREIGN KEY'" in sql: return Result(self.fks)
        if "constraint_type = 'UNIQUE'" in sql: return Result(self.uniques)
        if "FROM pg_constraint" in sql: return Result(self.checks)
        if "FROM pg_indexes" in sql: return Result(self.indexes)
        if "information_schema.triggers" in sql: return Result(self.triggers)
        return Result([])


def test_registry_and_migration_identity():
    assert MIGRATION_VERSION == 177
    assert MIGRATION_NAME == "create_subject_room_requirements_v2"
    assert POSTGRES_MIGRATIONS[-11].version == 177
    assert [m.version for m in POSTGRES_MIGRATIONS] == list(range(100, 188))
    assert migration().version == 177


def test_effective_sqlite_schema_is_preserved():
    assert list(_EXPECTED_COLUMNS) == ['id', 'tenant_id', 'school_id', 'subject_id', 'room_id', 'requirement_type', 'status', 'client_uuid', 'updated_at', 'is_deleted']
    sql = MIGRATION_SOURCE.lower()
    for fragment in (
        "tenant_id text not null",
        "school_id integer not null",
        "subject_id integer not null",
        "room_id bigint not null",
        "requirement_type text not null",
        "status text not null default 'active'",
        "client_uuid text",
        "updated_at text",
        "is_deleted bigint default 0",
        "unique (tenant_id, school_id, subject_id, room_id)",
        "references schools(id)",
        "references subjects(id)",
        "references timetable_rooms_v2(id)",
        "where client_uuid is not null", "before insert", "before update",
    ):
        assert fragment in sql
    assert sql.count("references ") == 3
    assert "check (" not in sql


def test_apply_executes_every_statement_and_validates():
    conn = FakeConnection()
    apply_subject_room_requirements_v2(conn)
    executed = [sql for sql, _ in conn.calls]
    for statement in MIGRATION_STATEMENTS:
        assert statement in executed


@pytest.mark.parametrize("parent,bad_type", [("schools", "bigint"), ("subjects", "bigint"), ("timetable_rooms_v2", "integer")])
def test_rejects_incompatible_parent_key_type(parent, bad_type):
    with pytest.raises(RuntimeError, match=f"{parent}.id"):
        apply_subject_room_requirements_v2(FakeConnection(parent_types={parent: bad_type}))


def test_rejects_missing_foreign_keys():
    with pytest.raises(RuntimeError, match="foreign keys incompatible"):
        apply_subject_room_requirements_v2(FakeConnection(fks=[]))


def test_rejects_wrong_columns():
    with pytest.raises(RuntimeError, match="columns incompatible"):
        apply_subject_room_requirements_v2(FakeConnection(columns=[]))


def test_rejects_wrong_unique_constraint():
    with pytest.raises(RuntimeError, match="unique constraints incompatible"):
        apply_subject_room_requirements_v2(FakeConnection(uniques=[]))
    reordered = [{"constraint_name": "uq_x", "column_name": c, "ordinal_position": i}
                 for i, c in enumerate(('room_id', 'school_id', 'subject_id', 'tenant_id'), 1)]
    with pytest.raises(RuntimeError, match="unique constraints incompatible"):
        apply_subject_room_requirements_v2(FakeConnection(uniques=reordered))


def test_rejects_unexpected_check_constraint():
    with pytest.raises(RuntimeError, match="CHECK constraints incompatible"):
        apply_subject_room_requirements_v2(FakeConnection(checks=[{"conname": "x"}]))


def test_rejects_wrong_indexes():
    with pytest.raises(RuntimeError, match="indexes incompatible"):
        apply_subject_room_requirements_v2(FakeConnection(indexes=[]))


def test_rejects_non_partial_client_uuid_index():
    bad = [
        {"indexname": "subject_room_requirements_v2_pkey", "indexdef": "x"},
        {"indexname": "uq_subject_room_requirements_v2_subject_room", "indexdef": "x"},
        {"indexname": "idx_subject_room_requirements_v2_client_uuid", "indexdef": "CREATE INDEX i ON t USING btree (client_uuid)"},
    ]
    with pytest.raises(RuntimeError, match="partial index"):
        apply_subject_room_requirements_v2(FakeConnection(indexes=bad))


def test_rejects_wrong_triggers():
    with pytest.raises(RuntimeError, match="triggers incompatible"):
        apply_subject_room_requirements_v2(FakeConnection(triggers=[]))
