from datetime import UTC, date, datetime, timedelta, timezone

# 한국은 서머타임이 없어 고정 오프셋으로 충분하다 (Windows는 zoneinfo용 tz 데이터도 없다)
KST = timezone(timedelta(hours=9))


def today_kst(now: datetime | None = None) -> date:
    return (now or datetime.now(UTC)).astimezone(KST).date()
