import pytest

from postgres_migration_111_billing_job_runs import (
    MIGRATION_NAME, MIGRATION_SOURCE, MIGRATION_VERSION,
    apply_billing_job_runs, migration,
)
from postgres_migration_registry import POSTGRES_MIGRATIONS


class Result:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, columns=None, constraints=None, indexes=None, triggers=None):
        expected = {
            "id": "bigint", "job_name": "text", "started_at": "text",
            "finished_at": "text", "status": "text", "result_json": "text",
            "error_message": "text",
        }
        required = {"id", "job_name", "started_at", "status"}
        self.columns = columns if columns is not None else [
            {"column_name": name, "data_type": dtype,
             "is_nullable": "NO" if name in required else "YES"}
            for name, dtype in expected.items()
        ]
        self.constraints = constraints or []
        self.indexes = indexes if indexes is not None else [
            {"indexname": "billing_job_runs_pkey", "indexdef": "CREATE UNIQUE INDEX billing_job_runs_pkey ON public.billing_job_runs USING btree (id)"},
            {"indexname": "idx_billing_job_runs_status", "indexdef": "CREATE INDEX idx_billing_job_runs_status ON public.billing_job_runs USING btree (status)"},
            {"indexname": "idx_billing_job_runs_name_started", "indexdef": "CREATE INDEX idx_billing_job_runs_name_started ON public.billing_job_runs USING btree (job_name, started_at)"},
        ]
        self.triggers = triggers or []
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


def test_billing_job_runs_migration_is_registered_in_order():
    assert MIGRATION_VERSION == 111
    assert MIGRATION_NAME == "create_billing_job_runs"
    assert [item.version for item in POSTGRES_MIGRATIONS] == list(range(100, 143))
    assert next(item for item in POSTGRES_MIGRATIONS if item.version == MIGRATION_VERSION).name == MIGRATION_NAME


def test_billing_job_runs_ddl_preserves_source_contract():
    sql = MIGRATION_SOURCE.lower()
    for column in ("job_name", "started_at", "finished_at", "status", "result_json", "error_message"):
        assert column in sql
    assert "started_at text not null default current_timestamp" in sql
    assert "status text not null default 'running'" in sql
    assert "idx_billing_job_runs_status on billing_job_runs (status)" in sql
    assert "idx_billing_job_runs_name_started on billing_job_runs (job_name, started_at)" in sql
    assert "references " not in sql
    assert "create trigger" not in sql


def test_apply_validates_expected_schema_and_indexes():
    conn = FakeConnection()
    apply_billing_job_runs(conn)
    assert len(conn.calls) == 7  # three DDL statements plus four catalog checks


def test_apply_rejects_missing_columns_foreign_keys_and_extra_indexes():
    columns = [row for row in FakeConnection().columns if row["column_name"] != "result_json"]
    with pytest.raises(RuntimeError, match="missing columns"):
        apply_billing_job_runs(FakeConnection(columns=columns))

    with pytest.raises(RuntimeError, match="foreign-key"):
        apply_billing_job_runs(FakeConnection(constraints=[{"constraint_type": "FOREIGN KEY"}]))

    extra = FakeConnection().indexes + [{"indexname": "unexpected_idx", "indexdef": "CREATE INDEX unexpected_idx ON billing_job_runs (status)"}]
    with pytest.raises(RuntimeError, match="indexes are incompatible"):
        apply_billing_job_runs(FakeConnection(indexes=extra))


def test_migration_metadata():
    item = migration()
    assert item.version == MIGRATION_VERSION
    assert item.name == MIGRATION_NAME
    assert item.source == MIGRATION_SOURCE
    assert callable(item.apply)
