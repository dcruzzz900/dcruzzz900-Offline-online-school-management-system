import pytest

from postgres_migration_173_timetable_versions_v2 import (
    MIGRATION_NAME, MIGRATION_SOURCE, MIGRATION_STATEMENTS, MIGRATION_VERSION,
    _EXPECTED_COLUMNS, apply_timetable_versions_v2, migration,
)
from postgres_migration_registry import POSTGRES_MIGRATIONS

UNIQUE_COLUMNS = ('tenant_id', 'school_id', 'version_number')


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
        ]
        self.uniques = uniques if uniques is not None else [
            {"constraint_name": "uq_timetable_versions_v2_version_number", "column_name": c, "ordinal_position": i}
            for i, c in enumerate(UNIQUE_COLUMNS, 1)
        ]
        self.checks = checks if checks is not None else []
        self.indexes = indexes if indexes is not None else [
            {"indexname": "timetable_versions_v2_pkey", "indexdef": "CREATE UNIQUE INDEX timetable_versions_v2_pkey ON public.timetable_versions_v2 USING btree (id)"},
            {"indexname": "uq_timetable_versions_v2_version_number", "indexdef": "CREATE UNIQUE INDEX uq_timetable_versions_v2_version_number ON public.timetable_versions_v2 USING btree (tenant_id, school_id, version_number)"},
            {"indexname": "idx_timetable_versions_v2_client_uuid", "indexdef": "CREATE UNIQUE INDEX idx_timetable_versions_v2_client_uuid ON public.timetable_versions_v2 USING btree (client_uuid) WHERE (client_uuid IS NOT NULL)"},
        ]
        self.triggers = triggers if triggers is not None else [
            {"trigger_name": "trg_timetable_versions_v2_sync_defaults"}, {"trigger_name": "trg_timetable_versions_v2_sync_touch"}]
        self.parent_types = {"schools": "integer"}
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
    assert MIGRATION_VERSION == 173
    assert MIGRATION_NAME == "create_timetable_versions_v2"
    assert POSTGRES_MIGRATIONS[-15].version == 173
    assert [m.version for m in POSTGRES_MIGRATIONS] == list(range(100, 188))
    assert migration().version == 173


def test_effective_sqlite_schema_is_preserved():
    assert list(_EXPECTED_COLUMNS) == ['id', 'tenant_id', 'school_id', 'academic_session_id', 'term_id', 'timetable_type_id', 'version_number', 'status', 'validation_status', 'is_current', 'parent_version_id', 'created_by', 'created_at', 'updated_by', 'updated_at', 'submitted_by', 'submitted_at', 'published_by', 'published_at', 'archived_at', 'revision_reason', 'client_uuid', 'is_deleted']
    sql = MIGRATION_SOURCE.lower()
    for fragment in (
        "tenant_id text not null",
        "school_id integer not null",
        "academic_session_id bigint",
        "term_id bigint",
        "timetable_type_id bigint",
        "version_number bigint not null",
        "status text not null default 'draft'",
        "validation_status text not null default 'pending'",
        "is_current bigint default 1",
        "parent_version_id bigint",
        "created_by bigint",
        "created_at text default current_timestamp",
        "updated_by bigint",
        "updated_at text default current_timestamp",
        "submitted_by bigint",
        "submitted_at text",
        "published_by bigint",
        "published_at text",
        "archived_at text",
        "revision_reason text",
        "client_uuid text",
        "is_deleted bigint default 0",
        "unique (tenant_id, school_id, version_number)",
        "references schools(id)",
        "where client_uuid is not null", "before insert", "before update",
    ):
        assert fragment in sql
    assert sql.count("references ") == 1
    assert "check (" not in sql


def test_apply_executes_every_statement_and_validates():
    conn = FakeConnection()
    apply_timetable_versions_v2(conn)
    executed = [sql for sql, _ in conn.calls]
    for statement in MIGRATION_STATEMENTS:
        assert statement in executed


@pytest.mark.parametrize("parent,bad_type", [("schools", "bigint")])
def test_rejects_incompatible_parent_key_type(parent, bad_type):
    with pytest.raises(RuntimeError, match=f"{parent}.id"):
        apply_timetable_versions_v2(FakeConnection(parent_types={parent: bad_type}))


def test_rejects_missing_foreign_keys():
    with pytest.raises(RuntimeError, match="foreign keys incompatible"):
        apply_timetable_versions_v2(FakeConnection(fks=[]))


def test_rejects_wrong_columns():
    with pytest.raises(RuntimeError, match="columns incompatible"):
        apply_timetable_versions_v2(FakeConnection(columns=[]))


def test_rejects_wrong_unique_constraint():
    with pytest.raises(RuntimeError, match="unique constraints incompatible"):
        apply_timetable_versions_v2(FakeConnection(uniques=[]))
    reordered = [{"constraint_name": "uq_x", "column_name": c, "ordinal_position": i}
                 for i, c in enumerate(('version_number', 'school_id', 'tenant_id'), 1)]
    with pytest.raises(RuntimeError, match="unique constraints incompatible"):
        apply_timetable_versions_v2(FakeConnection(uniques=reordered))


def test_rejects_unexpected_check_constraint():
    with pytest.raises(RuntimeError, match="CHECK constraints incompatible"):
        apply_timetable_versions_v2(FakeConnection(checks=[{"conname": "x"}]))


def test_rejects_wrong_indexes():
    with pytest.raises(RuntimeError, match="indexes incompatible"):
        apply_timetable_versions_v2(FakeConnection(indexes=[]))


def test_rejects_non_partial_client_uuid_index():
    bad = [
        {"indexname": "timetable_versions_v2_pkey", "indexdef": "x"},
        {"indexname": "uq_timetable_versions_v2_version_number", "indexdef": "x"},
        {"indexname": "idx_timetable_versions_v2_client_uuid", "indexdef": "CREATE INDEX i ON t USING btree (client_uuid)"},
    ]
    with pytest.raises(RuntimeError, match="partial index"):
        apply_timetable_versions_v2(FakeConnection(indexes=bad))


def test_rejects_wrong_triggers():
    with pytest.raises(RuntimeError, match="triggers incompatible"):
        apply_timetable_versions_v2(FakeConnection(triggers=[]))
