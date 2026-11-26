import pytest

from postgres_migration_ops import add_column_if_missing


class Result:
    def __init__(self, rows): self.rows = rows
    def fetchone(self): return self.rows[0] if self.rows else None
    def fetchall(self): return self.rows


class FakeConnection:
    def __init__(self, columns=None, table=True):
        self.columns = [dict(row, udt_name=row.get("udt_name", ""), is_nullable=row.get("is_nullable", "YES"), column_default=row.get("column_default"), ordinal_position=row.get("ordinal_position", 1)) for row in (columns or [])]
        self.table = table
        self.calls = []
    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        if "information_schema.tables" in sql:
            return Result([{"present": self.table}])
        if "information_schema.columns" in sql and "column_name, data_type" in sql:
            return Result(self.columns)
        if "information_schema.columns" in sql:
            return Result([{"column_name": row["column_name"]} for row in self.columns])
        return Result([])


def test_adds_nullable_column_with_quoted_identifiers():
    conn = FakeConnection()
    result = add_column_if_missing(conn, "students", "custom_note", "TEXT", schema="public")
    assert result == "added"
    ddl = conn.calls[-1][0]
    assert ddl == 'ALTER TABLE "public"."students" ADD COLUMN "custom_note" TEXT'


def test_adds_not_null_column_only_with_safe_default():
    conn = FakeConnection()
    assert add_column_if_missing(conn, "schools", "enabled", "BOOLEAN", nullable=False, default_sql="TRUE") == "added"
    assert 'DEFAULT TRUE NOT NULL' in conn.calls[-1][0]


def test_existing_matching_column_is_idempotent():
    conn = FakeConnection([{"column_name": "name", "data_type": "text"}])
    assert add_column_if_missing(conn, "schools", "name", "TEXT") == "existing"
    assert not any(sql.startswith("ALTER TABLE") for sql, _ in conn.calls)


def test_existing_wrong_type_fails_closed():
    conn = FakeConnection([{"column_name": "enabled", "data_type": "text"}])
    with pytest.raises(TypeError, match="expected 'boolean'"):
        add_column_if_missing(conn, "schools", "enabled", "BOOLEAN")


def test_missing_table_fails_closed():
    with pytest.raises(LookupError):
        add_column_if_missing(FakeConnection(table=False), "schools", "extra", "TEXT")


@pytest.mark.parametrize("bad_type", ["TEXT; DROP TABLE students", "VARCHAR(255)", "INTEGER DEFAULT 1"])
def test_unreviewed_types_are_rejected(bad_type):
    with pytest.raises(ValueError):
        add_column_if_missing(FakeConnection(), "students", "x", bad_type)


@pytest.mark.parametrize("bad_default", ["now()", "other_column", "1); DROP TABLE students; --"])
def test_expression_defaults_are_rejected(bad_default):
    with pytest.raises(ValueError):
        add_column_if_missing(FakeConnection(), "students", "x", "TEXT", default_sql=bad_default)


def test_not_null_without_default_is_rejected():
    with pytest.raises(ValueError, match="requires an explicit safe default"):
        add_column_if_missing(FakeConnection(), "students", "required", "TEXT", nullable=False)


def test_invalid_identifier_is_rejected():
    with pytest.raises(ValueError):
        add_column_if_missing(FakeConnection(), "students; DROP TABLE users", "x", "TEXT")
