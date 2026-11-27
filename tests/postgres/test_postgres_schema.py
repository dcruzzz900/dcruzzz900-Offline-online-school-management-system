import pytest

from postgres_schema import (
    acquire_migration_lock,
    column_info,
    column_names,
    index_exists,
    table_exists,
)


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        return FakeResult(self.responses.pop(0) if self.responses else [])


def test_table_exists_uses_current_schema_and_bound_table_name():
    conn = FakeConnection([[{"present": True}]])
    assert table_exists(conn, "students") is True
    assert "current_schema()" in conn.calls[0][0]
    assert conn.calls[0][1] == ("students",)


def test_table_exists_supports_explicit_schema():
    conn = FakeConnection([[(False,)]])
    assert table_exists(conn, "students", "tenant_data") is False
    assert conn.calls[0][1] == ("tenant_data", "students")


def test_column_names_preserve_ordinal_order():
    conn = FakeConnection([[{"column_name": "id"}, {"column_name": "school_id"}]])
    assert column_names(conn, "students") == ["id", "school_id"]
    assert "ORDER BY ordinal_position" in conn.calls[0][0]


def test_column_info_returns_reviewable_type_metadata():
    row = {
        "column_name": "active",
        "data_type": "boolean",
        "udt_name": "bool",
        "is_nullable": "NO",
        "column_default": "true",
        "ordinal_position": 3,
    }
    conn = FakeConnection([[row]])
    assert column_info(conn, "students")[0] == row


def test_index_exists_queries_pg_indexes():
    conn = FakeConnection([[(True,)]])
    assert index_exists(conn, "idx_students_school") is True
    assert "pg_indexes" in conn.calls[0][0]


def test_advisory_lock_is_transaction_scoped_and_parameterized():
    conn = FakeConnection([[]])
    acquire_migration_lock(conn, 123456)
    assert "pg_advisory_xact_lock(?)" in conn.calls[0][0]
    assert conn.calls[0][1] == (123456,)


@pytest.mark.parametrize("bad", [True, "123", 1.5, None])
def test_advisory_lock_rejects_non_integer_keys(bad):
    with pytest.raises(TypeError):
        acquire_migration_lock(FakeConnection(), bad)


def test_advisory_lock_rejects_out_of_range_key():
    with pytest.raises(ValueError):
        acquire_migration_lock(FakeConnection(), 2**63)
