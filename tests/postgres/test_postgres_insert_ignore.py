import pytest

from postgres_dbapi import PostgresCursorAdapter, translate_insert_ignore


class RecordingCursor:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return self


def test_insert_or_ignore_becomes_postgres_do_nothing():
    sql = "INSERT OR IGNORE INTO enrollments(student_id, class_id) VALUES (?, ?)"
    assert translate_insert_ignore(sql) == (
        "INSERT INTO enrollments(student_id, class_id) VALUES (?, ?) ON CONFLICT DO NOTHING"
    )


def test_insert_ignore_preserves_leading_whitespace_and_case():
    assert translate_insert_ignore("  insert or ignore into x(a) values (?)") == (
        "  INSERT INTO x(a) values (?) ON CONFLICT DO NOTHING"
    )


def test_regular_insert_is_unchanged():
    sql = "INSERT INTO x(a) VALUES (?)"
    assert translate_insert_ignore(sql) == sql


def test_insert_or_replace_fails_closed():
    with pytest.raises(NotImplementedError, match="explicit conflict target"):
        translate_insert_ignore("INSERT OR REPLACE INTO x(a) VALUES (?)")


def test_existing_conflict_clause_is_rejected():
    with pytest.raises(ValueError, match="existing ON CONFLICT"):
        translate_insert_ignore("INSERT OR IGNORE INTO x(a) VALUES (?) ON CONFLICT (a) DO UPDATE SET a=1")


def test_adapter_translates_before_qmark_conversion():
    cursor = RecordingCursor()
    PostgresCursorAdapter(cursor).execute(
        "INSERT OR IGNORE INTO x(a, b) VALUES (?, ?)", (1, 2)
    )
    assert cursor.calls == [
        ("INSERT INTO x(a, b) VALUES (%s, %s) ON CONFLICT DO NOTHING", (1, 2))
    ]
