from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session


def insert(
    db: Session,
    zone_id: int,
    pest_id: int | None,
    pesticide_id: int,
    apply_date: date,
    verdict: str,
    result_json: str,
) -> int:
    """판정 한 건을 저장하고 id를 돌려준다. 커밋은 호출하는 쪽이 한다."""
    return db.scalar(
        text(
            "INSERT INTO judgment (zone_id, pest_id, pesticide_id, apply_date, verdict, result) "
            "VALUES (:zone, :pest, :drug, :day, :verdict, CAST(:result AS jsonb)) "
            "RETURNING id"
        ),
        {
            "zone": zone_id,
            "pest": pest_id,
            "drug": pesticide_id,
            "day": apply_date,
            "verdict": verdict,
            "result": result_json,
        },
    )


def recent(db: Session, zone_id: int, limit: int):
    """구역의 판정을 최신순으로 limit건. 같은 시각이면 id가 큰 쪽이 먼저다."""
    return db.execute(
        text(
            "SELECT id, zone_id, pest_id, pesticide_id, verdict, created_at FROM judgment "
            "WHERE zone_id = :zone ORDER BY created_at DESC, id DESC LIMIT :n"
        ),
        {"zone": zone_id, "n": limit},
    ).all()


def latest_per_zone(db: Session, zone_ids: list[int]):
    """구역마다 가장 최근 판정 한 건 (쿼리 1번). 판정이 없는 구역은 빠진다."""
    if not zone_ids:
        return []
    return db.execute(
        text(
            "SELECT DISTINCT ON (zone_id) id, zone_id, pest_id, pesticide_id, verdict, created_at "
            "FROM judgment WHERE zone_id = ANY(:ids) ORDER BY zone_id, created_at DESC, id DESC"
        ),
        {"ids": zone_ids},
    ).all()
