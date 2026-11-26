"""Small cross-dialect helpers for database operations shared by SQLite and PostgreSQL."""
from __future__ import annotations


def insert_returning_id(cursor, sql: str, params=(), *, key: str = "id") -> int:
    """Execute one INSERT and return its generated key on either backend.

    PostgreSQL cursors must expose ``execute_returning_id``; SQLite cursors use
    the native ``lastrowid``. This explicit helper avoids pretending that
    PostgreSQL supports SQLite's implicit lastrowid contract.
    """
    pg_method = getattr(cursor, "execute_returning_id", None)
    if callable(pg_method):
        return pg_method(sql, params, key=key)
    result = cursor.execute(sql, params) if params is not None else cursor.execute(sql)
    value = getattr(result, "lastrowid", None)
    if value is None:
        raise RuntimeError("INSERT did not return a generated row id")
    return value


def utc_today_iso():
    """Return today's UTC calendar date as YYYY-MM-DD (SQLite date('now') equivalent)."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).date().isoformat()


def utc_date_days_ago_iso(days: int) -> str:
    """Return a UTC calendar date N days ago as YYYY-MM-DD."""
    from datetime import date, timedelta

    if isinstance(days, bool) or not isinstance(days, int) or days < 0:
        raise ValueError("days must be a non-negative integer")
    return (date.fromisoformat(utc_today_iso()) - timedelta(days=days)).isoformat()


def days_between_iso_dates(start_date, end_date) -> int | None:
    """Whole calendar days from start_date to end_date; None for absent/invalid input."""
    from datetime import date

    if not start_date or not end_date:
        return None
    try:
        start = date.fromisoformat(str(start_date)[:10])
        end = date.fromisoformat(str(end_date)[:10])
    except (TypeError, ValueError):
        return None
    return (end - start).days
