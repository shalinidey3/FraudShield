from app import format_timestamp, get_today_date, APP_TIMEZONE
from datetime import datetime, timezone, timedelta


def test_format_timestamp_converts_utc_to_local_timezone():
    assert format_timestamp("2026-07-08 18:53:26") == "2026-07-09"


def test_get_today_date_matches_app_timezone():
    now = datetime.now(APP_TIMEZONE)
    expected = now.date().isoformat()
    assert get_today_date() == expected
