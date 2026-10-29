from datetime import date
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.spraying.domain.entities import Spray

_BIGINT_MAX = 2**63 - 1


def _spray(row) -> Spray:
    return Spray(row.id, row.pesticide_id, row.sprayed_on, row.source)


def find_by_request_id(db: Session, request_id: UUID) -> tuple[Spray, int] | None:
    """기록과 그 기록이 속한 구역 id."""
    row = db.execute(
        text(
            "SELECT id, pesticide_id, sprayed_on, source, zone_id "
            "FROM spray_log WHERE request_id = :rid"
        ),
        {"rid": request_id},
    ).one_or_none()
    return (_spray(row), row.zone_id) if row else None


def find_duplicate(db: Session, zone_id: int, pesticide_id: int, sprayed_on: date) -> Spray | None:
    """같은 구역·약제·날짜 기록 중 가장 먼저 저장된 것."""
    row = db.execute(
        text(
            "SELECT id, pesticide_id, sprayed_on, source FROM spray_log "
            "WHERE zone_id = :zone AND pesticide_id = :pid AND sprayed_on = :day "
            "ORDER BY id LIMIT 1"
        ),
        {"zone": zone_id, "pid": pesticide_id, "day": sprayed_on},
    ).one_or_none()
    return _spray(row) if row else None


def insert(
    db: Session,
    zone_id: int,
    pesticide_id: int,
    sprayed_on: date,
    source: str,
    request_id: UUID,
) -> Spray | None:
    """request_id가 이미 있으면 저장하지 않고 None."""
    row = db.execute(
        text(
            "INSERT INTO spray_log (zone_id, pesticide_id, sprayed_on, source, request_id) "
            "VALUES (:zone, :pid, :day, :source, :rid) "
            "ON CONFLICT (request_id) DO NOTHING "
            "RETURNING id, pesticide_id, sprayed_on, source"
        ),
        {
            "zone": zone_id,
            "pid": pesticide_id,
            "day": sprayed_on,
            "source": source,
            "rid": request_id,
        },
    ).one_or_none()
    return _spray(row) if row else None


def page(db: Session, zone_id: int, limit: int, offset: int) -> tuple[int, list[Spray]]:
    offset = min(offset, _BIGINT_MAX)  # 끝을 넘는 offset은 빈 페이지다 (bigint 밖이면 DB 오류)
    total = db.scalar(
        text("SELECT count(*) FROM spray_log WHERE zone_id = :zone"), {"zone": zone_id}
    )
    rows = db.execute(
        text(
            "SELECT id, pesticide_id, sprayed_on, source FROM spray_log "
            "WHERE zone_id = :zone ORDER BY sprayed_on DESC, id DESC "
            "LIMIT :limit OFFSET :offset"
        ),
        {"zone": zone_id, "limit": limit, "offset": offset},
    ).all()
    return total, [_spray(row) for row in rows]


def all_for_zone(db: Session, zone_id: int) -> list[Spray]:
    """구역의 기록 전체 (페이징 없음), 최근순."""
    rows = db.execute(
        text(
            "SELECT id, pesticide_id, sprayed_on, source FROM spray_log "
            "WHERE zone_id = :zone ORDER BY sprayed_on DESC, id DESC"
        ),
        {"zone": zone_id},
    ).all()
    return [_spray(row) for row in rows]


def delete(db: Session, zone_id: int, spray_id: int) -> bool:
    result = db.execute(
        text("DELETE FROM spray_log WHERE id = :id AND zone_id = :zone"),
        {"id": spray_id, "zone": zone_id},
    )
    return result.rowcount > 0
