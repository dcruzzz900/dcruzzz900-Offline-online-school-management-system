from datetime import date, timedelta

import pytest

from db_compat import days_between_iso_dates, utc_date_days_ago_iso, utc_today_iso


def test_utc_today_is_iso_calendar_date():
    value = utc_today_iso()
    assert date.fromisoformat(value).isoformat() == value


def test_utc_date_days_ago_returns_iso_date():
    today = date.fromisoformat(utc_today_iso())
    value = date.fromisoformat(utc_date_days_ago_iso(30))
    assert value == today - timedelta(days=30)


@pytest.mark.parametrize("invalid", [-1, True, 1.5, "30"])
def test_utc_date_days_ago_rejects_invalid_day_counts(invalid):
    with pytest.raises(ValueError):
        utc_date_days_ago_iso(invalid)


def test_days_between_iso_dates_handles_date_and_timestamp_values():
    assert days_between_iso_dates("2026-11-25", "2026-12-03") == 8
    assert days_between_iso_dates("2026-11-25 12:30:00", "2026-11-24") == -1


@pytest.mark.parametrize("start,end", [(None, "2026-11-25"), ("2026-11-25", None), ("bad", "2026-11-25")])
def test_days_between_iso_dates_returns_none_for_missing_or_invalid_values(start, end):
    assert days_between_iso_dates(start, end) is None
