from datetime import UTC, date, datetime

from app.core.time import today_kst


def test_today_kst_rolls_over_at_utc_1500():
    assert today_kst(datetime(2026, 10, 4, 14, 59, tzinfo=UTC)) == date(2026, 10, 4)
    assert today_kst(datetime(2026, 10, 4, 15, 0, tzinfo=UTC)) == date(2026, 10, 5)
