"""PostgreSQL catalog helpers for a future dialect-aware migration runner.

These helpers intentionally do not replace db.py's SQLite migration functions.
They provide PostgreSQL-native, parameterized catalog inspection and a
transaction-scoped advisory lock for the eventual PostgreSQL migration runner.
"""
from __future__ import annotations

from typing import Any


def _row_value(row: Any, key: str, index: int = 0):
    if row is None:
        return None
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return row[index]


def table_exists(conn, table: str, schema: str | None = None) -> bool:
    """Return whether a table exists in the selected/current schema."""
    if schema is None:
        row = conn.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = current_schema() AND table_name = ?) AS present",
            (table,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = ? AND table_name = ?) AS present",
            (schema, table),
        ).fetchone()
    return bool(_row_value(row, "present")) if row is not None else False


def column_names(conn, table: str, schema: str | None = None) -> list[str]:
    """Return columns in physical ordinal order for a PostgreSQL table."""
    if schema is None:
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = ? "
            "ORDER BY ordinal_position",
            (table,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = ? AND table_name = ? ORDER BY ordinal_position",
            (schema, table),
        ).fetchall()
    return [str(_row_value(row, "column_name")) for row in rows]


def column_info(conn, table: str, schema: str | None = None) -> list[dict[str, Any]]:
    """Return portable PostgreSQL column metadata useful for migration checks."""
    fields = "column_name, data_type, udt_name, is_nullable, column_default, ordinal_position"
    if schema is None:
        rows = conn.execute(
            f"SELECT {fields} FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = ? "
            "ORDER BY ordinal_position",
            (table,),
        ).fetchall()
    else:
        rows = conn.execute(
            f"SELECT {fields} FROM information_schema.columns "
            "WHERE table_schema = ? AND table_name = ? ORDER BY ordinal_position",
            (schema, table),
        ).fetchall()
    keys = fields.split(", ")
    result = []
    for row in rows:
        if hasattr(row, "keys"):
            result.append({key: row[key] for key in keys})
        else:
            result.append(dict(zip(keys, row)))
    return result


def index_exists(conn, index: str, schema: str | None = None) -> bool:
    """Return whether an index exists in the selected/current schema."""
    if schema is None:
        row = conn.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_indexes "
            "WHERE schemaname = current_schema() AND indexname = ?) AS present",
            (index,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_indexes "
            "WHERE schemaname = ? AND indexname = ?) AS present",
            (schema, index),
        ).fetchone()
    return bool(_row_value(row, "present")) if row is not None else False


def acquire_migration_lock(conn, lock_key: int) -> None:
    """Serialize migrations using a transaction-scoped PostgreSQL advisory lock.

    The caller must keep the transaction open until the migration completes.
    PostgreSQL releases this lock automatically on COMMIT or ROLLBACK.
    """
    if isinstance(lock_key, bool) or not isinstance(lock_key, int):
        raise TypeError("lock_key must be an integer")
    if not -(2**63) <= lock_key < 2**63:
        raise ValueError("lock_key must fit a signed 64-bit integer")
    conn.execute("SELECT pg_advisory_xact_lock(?)", (lock_key,))


def validate_schema_shape(conn, required_tables: dict[str, list[str]], schema: str | None = None) -> dict[str, Any]:
    """Validate required table/column names without changing the target database.

    Extra tables and columns are reported but allowed: an existing installation
    may contain deployment-specific extensions. Missing required objects fail
    the readiness check. This function never creates, alters, truncates, or
    deletes data and is safe to run before a migration or data-copy operation.
    """
    if not isinstance(required_tables, dict) or not required_tables:
        raise ValueError("required_tables must be a non-empty table-to-columns mapping")

    missing_tables: list[str] = []
    missing_columns: dict[str, list[str]] = {}
    extra_columns: dict[str, list[str]] = {}
    present_tables: list[str] = []

    for table, required_columns in sorted(required_tables.items()):
        if not isinstance(table, str) or not table.strip():
            raise ValueError("table names must be non-empty strings")
        if not isinstance(required_columns, list) or any(
            not isinstance(column, str) or not column.strip() for column in required_columns
        ):
            raise ValueError(f"required columns for {table!r} must be a list of non-empty strings")
        if not table_exists(conn, table, schema):
            missing_tables.append(table)
            continue
        present_tables.append(table)
        actual = set(column_names(conn, table, schema))
        required = set(required_columns)
        absent = sorted(required - actual)
        additional = sorted(actual - required)
        if absent:
            missing_columns[table] = absent
        if additional:
            extra_columns[table] = additional

    return {
        "ok": not missing_tables and not missing_columns,
        "required_table_count": len(required_tables),
        "present_table_count": len(present_tables),
        "missing_tables": missing_tables,
        "missing_columns": missing_columns,
        "extra_columns": extra_columns,
        "schema": schema or "current_schema",
        "read_only": True,
    }
