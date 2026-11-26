import sqlite3

import pytest

from db_compat import insert_returning_id
from postgres_dbapi import PostgresCursorAdapter


def test_insert_returning_id_uses_sqlite_lastrowid():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)")
    value = insert_returning_id(conn.cursor(), "INSERT INTO sample(name) VALUES (?)", ("one",))
    assert value == 1
    assert conn.execute("SELECT name FROM sample WHERE id=?", (value,)).fetchone()[0] == "one"


class FakeCursor:
    def __init__(self, row=(42,)):
        self.row = row
        self.sql = None
        self.params = None
    def execute(self, sql, params=None):
        self.sql, self.params = sql, params
        return self
    def fetchone(self):
        return self.row


def test_postgres_adapter_uses_explicit_returning_id():
    raw = FakeCursor()
    cursor = PostgresCursorAdapter(raw)
    value = insert_returning_id(cursor, "INSERT INTO sample(name) VALUES (?)", ("one",))
    assert value == 42
    assert raw.sql.endswith("RETURNING id")
    assert "%s" in raw.sql


def test_postgres_returning_rejects_non_insert():
    cursor = PostgresCursorAdapter(FakeCursor())
    with pytest.raises(ValueError):
        cursor.execute_returning_id("UPDATE sample SET name=?", ("x",))


def test_postgres_returning_rejects_existing_returning_clause():
    cursor = PostgresCursorAdapter(FakeCursor())
    with pytest.raises(ValueError):
        cursor.execute_returning_id("INSERT INTO sample(name) VALUES (?) RETURNING id", ("x",))


def test_postgres_returning_rejects_invalid_column_identifier():
    cursor = PostgresCursorAdapter(FakeCursor())
    with pytest.raises(ValueError):
        cursor.execute_returning_id("INSERT INTO sample(name) VALUES (?)", ("x",), key="id; DROP TABLE sample")


def test_postgres_returning_requires_inserted_row():
    cursor = PostgresCursorAdapter(FakeCursor(row=None))
    with pytest.raises(RuntimeError):
        cursor.execute_returning_id("INSERT INTO sample(name) VALUES (?)", ("x",))
