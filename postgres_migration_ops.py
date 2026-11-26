"""Conservative PostgreSQL DDL helpers for explicitly reviewed migrations.

These helpers are deliberately separate from db.py's SQLite migration path.
They support additive column changes only; table rebuilds, data backfills,
foreign-key changes, and trigger conversion require dedicated migrations.
"""
from __future__ import annotations

import re

from postgres_schema import column_info, table_exists

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ALLOWED_TYPES = {
    "BIGINT": "bigint",
    "INTEGER": "integer",
    "SMALLINT": "smallint",
    "TEXT": "text",
    "BOOLEAN": "boolean",
    "DATE": "date",
    "TIMESTAMP": "timestamp without time zone",
    "TIMESTAMPTZ": "timestamp with time zone",
    "JSONB": "jsonb",
    "BYTEA": "bytea",
    "DOUBLE PRECISION": "double precision",
}
_DEFAULT_LITERAL = re.compile(
    r"^(?:CURRENT_TIMESTAMP|CURRENT_DATE|TRUE|FALSE|NULL|-?\d+(?:\.\d+)?|'(?:[^']|'')*')$",
    re.IGNORECASE,
)


def _identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{label} must be a simple SQL identifier")
    return '"' + value + '"'


def add_column_if_missing(
    conn,
    table: str,
    column: str,
    pg_type: str,
    *,
    schema: str | None = None,
    nullable: bool = True,
    default_sql: str | None = None,
) -> str:
    """Add one explicitly typed column, returning ``added`` or ``existing``.

    Existing columns are accepted only when their PostgreSQL type matches.
    Non-null columns on populated tables must specify a reviewed constant or
    SQL timestamp/date default. Arbitrary expressions and identifiers are
    rejected to prevent unsafe DDL interpolation.
    """
    if not isinstance(nullable, bool):
        raise TypeError("nullable must be a boolean")
    normalized_type = " ".join(str(pg_type).upper().split())
    expected_data_type = _ALLOWED_TYPES.get(normalized_type)
    if expected_data_type is None:
        raise ValueError(f"Unsupported PostgreSQL type: {pg_type!r}")
    if default_sql is not None:
        if not isinstance(default_sql, str) or not _DEFAULT_LITERAL.fullmatch(default_sql.strip()):
            raise ValueError("default_sql must be a reviewed literal or CURRENT_TIMESTAMP/CURRENT_DATE")
        default_sql = default_sql.strip()
    if not nullable and default_sql is None:
        raise ValueError("A NOT NULL additive column requires an explicit safe default")

    table_q = _identifier(table, "table")
    column_q = _identifier(column, "column")
    schema_q = _identifier(schema, "schema") if schema is not None else None
    if not table_exists(conn, table, schema):
        raise LookupError(f"PostgreSQL table {table!r} does not exist")

    existing = next((item for item in column_info(conn, table, schema) if item["column_name"] == column), None)
    if existing is not None:
        actual_type = str(existing.get("data_type", "")).lower()
        if actual_type != expected_data_type:
            raise TypeError(
                f"Existing column {table}.{column} has type {actual_type!r}; "
                f"expected {expected_data_type!r}"
            )
        return "existing"

    pieces = [f"ALTER TABLE {schema_q + '.' if schema_q else ''}{table_q}", f"ADD COLUMN {column_q} {normalized_type}"]
    if default_sql is not None:
        pieces.append(f"DEFAULT {default_sql}")
    if not nullable:
        pieces.append("NOT NULL")
    conn.execute(" ".join(pieces))
    return "added"
