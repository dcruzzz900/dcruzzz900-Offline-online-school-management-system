import pytest

from postgres_schema import validate_schema_shape


class Result:
    def __init__(self, rows):
        self.rows = rows
    def fetchone(self):
        return self.rows[0] if self.rows else None
    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, tables):
        self.tables = tables
        self.statements = []
    def execute(self, sql, params=()):
        self.statements.append((sql, params))
        if "information_schema.tables" in sql:
            schema, table = ("public", params[0]) if len(params) == 1 else params
            return Result([{"present": table in self.tables and schema == "public"}])
        if "information_schema.columns" in sql:
            schema, table = ("public", params[0]) if len(params) == 1 else params
            return Result([{"column_name": name} for name in self.tables.get(table, [])] if schema == "public" else [])
        raise AssertionError(f"Unexpected SQL: {sql}")


def test_schema_readiness_accepts_required_shape_and_reports_extensions():
    conn = FakeConnection({"schools": ["id", "name", "custom_field"], "students": ["id", "school_id"]})
    result = validate_schema_shape(conn, {"schools": ["id", "name"], "students": ["id", "school_id"]})
    assert result["ok"] is True
    assert result["extra_columns"] == {"schools": ["custom_field"]}
    assert result["read_only"] is True


def test_schema_readiness_reports_missing_tables_and_columns():
    conn = FakeConnection({"schools": ["id"]})
    result = validate_schema_shape(conn, {"schools": ["id", "name"], "students": ["id"]})
    assert result["ok"] is False
    assert result["missing_tables"] == ["students"]
    assert result["missing_columns"] == {"schools": ["name"]}


def test_schema_readiness_does_not_issue_mutating_sql():
    conn = FakeConnection({"schools": ["id"]})
    validate_schema_shape(conn, {"schools": ["id"]})
    assert all(not sql.lstrip().upper().startswith(("CREATE", "ALTER", "DROP", "DELETE", "TRUNCATE", "INSERT", "UPDATE")) for sql, _ in conn.statements)


def test_schema_readiness_validates_manifest():
    with pytest.raises(ValueError):
        validate_schema_shape(FakeConnection({}), {})
    with pytest.raises(ValueError):
        validate_schema_shape(FakeConnection({}), {"schools": "id"})
