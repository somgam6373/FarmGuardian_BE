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
