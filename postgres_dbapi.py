"""Pooled psycopg connection adapter for the application's DB-API conventions.

This is an opt-in integration component. It is intentionally NOT selected by
``db.get_db()`` yet: PostgreSQL schema migrations, SQLite-specific SQL, and
INSERT ``lastrowid`` call sites still need explicit conversion and tests.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Iterable

from postgres_compat import qmark_to_format
from postgres_pool import get_postgres_pool


def translate_db_exception(exc: BaseException, psycopg_module=None):
    """Map psycopg 3 DB-API exceptions to sqlite3 equivalents.

    Existing routes catch ``sqlite3.IntegrityError`` and related classes.  This
    narrow mapping preserves those catch paths when PostgreSQL is enabled,
    while leaving non-database and unknown exceptions untouched.  The import
    is lazy so SQLite-only deployments do not need psycopg installed.
    """
    if psycopg_module is None:
        try:
            import psycopg as psycopg_module
        except ImportError:
            return None

    mapping = (
        ("IntegrityError", sqlite3.IntegrityError),
        ("OperationalError", sqlite3.OperationalError),
        ("ProgrammingError", sqlite3.ProgrammingError),
        ("DataError", sqlite3.DataError),
        ("InterfaceError", sqlite3.InterfaceError),
        ("DatabaseError", sqlite3.DatabaseError),
        ("Error", sqlite3.Error),
    )
    for source_name, target_type in mapping:
        source_type = getattr(psycopg_module, source_name, None)
        if isinstance(source_type, type) and isinstance(exc, source_type):
            return target_type(str(exc))
    return None


def _run_db_operation(operation, *args, **kwargs):
    try:
        return operation(*args, **kwargs)
    except Exception as exc:
        translated = translate_db_exception(exc)
        if translated is None:
            raise
        raise translated from exc


class HybridRow(tuple):
    """Tuple-compatible row supporting both row[0] and row['column_name']."""

    def __new__(cls, values, column_names):
        obj = super().__new__(cls, values)
        obj._column_indexes = {name: i for i, name in enumerate(column_names)}
        return obj

    def __getitem__(self, key):
        if isinstance(key, str):
            try:
                key = self._column_indexes[key]
            except KeyError as exc:
                raise IndexError(f"No such column: {key}") from exc
        return super().__getitem__(key)

    def keys(self):
        return self._column_indexes.keys()



def hybrid_row_factory(cursor):
    """psycopg row_factory returning rows compatible with sqlite3.Row access."""
    description = cursor.description or ()
    names = [column.name if hasattr(column, "name") else column[0] for column in description]

    def make_row(values):
        return HybridRow(values, names)

    return make_row


def translate_insert_ignore(sql: str) -> str:
    """Translate SQLite INSERT OR IGNORE into PostgreSQL ON CONFLICT DO NOTHING.

    The rewrite is intentionally limited to the leading INSERT clause. It
    refuses INSERT OR REPLACE because REPLACE has delete-and-insert semantics
    in SQLite and cannot safely be approximated by a generic PostgreSQL upsert.
    """
    import re

    if re.match(r"\s*INSERT\s+OR\s+REPLACE\b", sql, flags=re.IGNORECASE):
        raise NotImplementedError(
            "INSERT OR REPLACE requires an explicit conflict target and update policy"
        )
    if not re.match(r"\s*INSERT\s+OR\s+IGNORE\b", sql, flags=re.IGNORECASE):
        return sql
    rewritten = re.sub(
        r"^(\s*)INSERT\s+OR\s+IGNORE\s+INTO\b",
        r"\1INSERT INTO",
        sql,
        count=1,
        flags=re.IGNORECASE,
    )
    if re.search(r"\bON\s+CONFLICT\b", rewritten, flags=re.IGNORECASE):
        raise ValueError("INSERT OR IGNORE cannot be combined with an existing ON CONFLICT clause")
    return rewritten.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"


class PostgresCursorAdapter:
    """Translate positional qmarks and supported SQLite insert idioms."""

    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, sql: str, params=None):
        sql = translate_insert_ignore(sql)
        if params is None:
            _run_db_operation(self._cursor.execute, sql)
        else:
            _run_db_operation(self._cursor.execute, qmark_to_format(sql, params), params)
        return self

    def execute_returning_id(self, sql: str, params=(), *, key: str = "id"):
        """Execute an INSERT with an explicit PostgreSQL RETURNING key."""
        import re
        if not re.match(r"\s*INSERT\s+INTO\s+", sql, flags=re.IGNORECASE):
            raise ValueError("execute_returning_id accepts INSERT statements only")
        if re.search(r"\bRETURNING\b", sql, flags=re.IGNORECASE):
            raise ValueError("INSERT already has a RETURNING clause")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise ValueError("Invalid RETURNING column name")
        self.execute(sql.rstrip().rstrip(";") + f" RETURNING {key}", params)
        row = self.fetchone()
        if row is None:
            raise RuntimeError("INSERT returned no row; no generated id is available")
        return row[0]

    def executemany(self, sql: str, seq_of_params: Iterable):
        rows = list(seq_of_params)
        if rows:
            translated = qmark_to_format(sql, rows[0])
        else:
            translated = qmark_to_format(sql, ())
        _run_db_operation(self._cursor.executemany, translated, rows)
        return self

    def __getattr__(self, name):
        if name == "lastrowid":
            raise NotImplementedError(
                "PostgreSQL inserts must use RETURNING <primary_key>; lastrowid is not supported"
            )
        return getattr(self._cursor, name)


class PostgresConnectionAdapter:
    """A checked-out pooled connection with sqlite-like execute/transaction API.

    ``close()`` returns the connection to the pool; it does not close the
    underlying PostgreSQL connection. ``executescript`` and implicit
    ``lastrowid`` are deliberately unsupported to prevent silent data errors.
    """

    def __init__(self, pool=None):
        self._pool = pool or get_postgres_pool()
        self._connection_context = self._pool.connection()
        self._connection = self._connection_context.__enter__()
        self._closed = False

    def _ensure_open(self):
        if self._closed:
            raise RuntimeError("PostgreSQL connection adapter is closed")

    def execute(self, sql: str, params=None):
        self._ensure_open()
        cursor = self._connection.cursor()
        return PostgresCursorAdapter(cursor).execute(sql, params)

    def executemany(self, sql: str, seq_of_params: Iterable):
        self._ensure_open()
        cursor = self._connection.cursor()
        return PostgresCursorAdapter(cursor).executemany(sql, seq_of_params)

    def cursor(self):
        self._ensure_open()
        return PostgresCursorAdapter(self._connection.cursor())

    def commit(self):
        self._ensure_open()
        return _run_db_operation(self._connection.commit)

    def rollback(self):
        self._ensure_open()
        return _run_db_operation(self._connection.rollback)

    def close(self):
        if not self._closed:
            self._closed = True
            self._connection_context.__exit__(None, None, None)

    def executescript(self, _script):
        raise NotImplementedError(
            "executescript is SQLite-specific; PostgreSQL migrations must execute reviewed statements individually"
        )

    def __enter__(self):
        self._ensure_open()
        return self

    def __exit__(self, exc_type, exc, tb):
        if not self._closed:
            try:
                if exc_type is None:
                    self.commit()
                else:
                    self.rollback()
            finally:
                self.close()
        return False

    def __getattr__(self, name: str) -> Any:
        self._ensure_open()
        return getattr(self._connection, name)
