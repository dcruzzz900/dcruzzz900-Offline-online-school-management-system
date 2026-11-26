"""PostgreSQL information_schema helpers for gradual SQLite catalog removal.

These helpers are intentionally separate from db.py's SQLite migration path.
They accept a psycopg connection/adapter exposing execute() and never interpolate
untrusted identifiers into SQL; table/schema names are bound parameters.
"""
from __future__ import annotations


def table_exists(conn, table: str, schema: str = "public") -> bool:
    row = conn.execute(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = %s AND table_name = %s) AS present",
        (schema, table),
    ).fetchone()
    return bool(row["present"] if hasattr(row, "__getitem__") and not isinstance(row, tuple) else row[0])


def column_names(conn, table: str, schema: str = "public") -> list[str]:
    rows = conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position",
        (schema, table),
    ).fetchall()
    return [row["column_name"] if not isinstance(row, tuple) else row[0] for row in rows]


def index_exists(conn, index: str, schema: str = "public") -> bool:
    row = conn.execute(
        "SELECT EXISTS (SELECT 1 FROM pg_indexes "
        "WHERE schemaname = %s AND indexname = %s) AS present",
        (schema, index),
    ).fetchone()
    return bool(row["present"] if hasattr(row, "__getitem__") and not isinstance(row, tuple) else row[0])
