from datetime import date
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.spraying.domain.entities import Spray

_BIGINT_MAX = 2**63 - 1
_COLUMNS = "id, pesticide_id, sprayed_on, source, pest_id, cancelled_at"


def _spray(row) -> Spray:
    cancelled = row.cancelled_at is not None
    return Spray(row.id, row.pesticide_id, row.sprayed_on, row.source, row.pest_id, cancelled)


def find_by_request_id(db: Session, request_id: UUID) -> tuple[Spray, int] | None:
    """기록과 그 기록이 속한 구역 id. 취소된 기록도 찾는다 (재시도는 원본을 돌려받는다)."""
    row = db.execute(
        text(f"SELECT {_COLUMNS}, zone_id FROM spray_log WHERE request_id = :rid"),
        {"rid": request_id},
    ).one_or_none()
    return (_spray(row), row.zone_id) if row else None


def find_duplicate(db: Session, zone_id: int, pesticide_id: int, sprayed_on: date) -> Spray | None:
    """같은 구역·약제·날짜 기록 중 가장 먼저 저장된 것. 취소된 기록은 중복이 아니다."""
    row = db.execute(
        text(
            f"SELECT {_COLUMNS} FROM spray_log "
            "WHERE zone_id = :zone AND pesticide_id = :pid AND sprayed_on = :day "
            "AND cancelled_at IS NULL ORDER BY id LIMIT 1"
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
    pest_id: int | None = None,
) -> Spray | None:
    """request_id가 이미 있으면 저장하지 않고 None."""
    row = db.execute(
        text(
            "INSERT INTO spray_log "
            "(zone_id, pesticide_id, sprayed_on, source, request_id, pest_id) "
            "VALUES (:zone, :pid, :day, :source, :rid, :pest) "
            "ON CONFLICT (request_id) DO NOTHING "
            f"RETURNING {_COLUMNS}"
        ),
        {
            "zone": zone_id,
            "pid": pesticide_id,
            "day": sprayed_on,
            "source": source,
            "rid": request_id,
            "pest": pest_id,
        },
    ).one_or_none()
    return _spray(row) if row else None


def page(
    db: Session, zone_id: int, limit: int, offset: int, include_cancelled: bool = False
) -> tuple[int, list[Spray]]:
    offset = min(offset, _BIGINT_MAX)  # 끝을 넘는 offset은 빈 페이지다 (bigint 밖이면 DB 오류)
    where = "WHERE zone_id = :zone AND (:with_cancelled OR cancelled_at IS NULL)"
    total = db.scalar(
        text(f"SELECT count(*) FROM spray_log {where}"),
        {"zone": zone_id, "with_cancelled": include_cancelled},
    )
    rows = db.execute(
        text(
            f"SELECT {_COLUMNS} FROM spray_log {where} "
            "ORDER BY sprayed_on DESC, id DESC LIMIT :limit OFFSET :offset"
        ),
        {"zone": zone_id, "with_cancelled": include_cancelled, "limit": limit, "offset": offset},
    ).all()
    return total, [_spray(row) for row in rows]


def all_for_zone(db: Session, zone_id: int) -> list[Spray]:
    """구역의 취소되지 않은 기록 전체 (페이징 없음), 최근순."""
    rows = db.execute(
        text(
            f"SELECT {_COLUMNS} FROM spray_log "
            "WHERE zone_id = :zone AND cancelled_at IS NULL "
            "ORDER BY sprayed_on DESC, id DESC"
        ),
        {"zone": zone_id},
    ).all()
    return [_spray(row) for row in rows]


def cancel(db: Session, zone_id: int, spray_id: int) -> bool:
    """취소 시각은 처음 한 번만 찍는다. 이 구역의 기록이 아니면 False."""
    result = db.execute(
        text(
            "UPDATE spray_log SET cancelled_at = COALESCE(cancelled_at, now()) "
            "WHERE id = :id AND zone_id = :zone"
        ),
        {"id": spray_id, "zone": zone_id},
    )
    return result.rowcount > 0


def restore(db: Session, zone_id: int, spray_id: int) -> Spray | None:
    """취소를 되돌린 기록. 이 구역의 기록이 아니면 None."""
    row = db.execute(
        text(
            "UPDATE spray_log SET cancelled_at = NULL "
            f"WHERE id = :id AND zone_id = :zone RETURNING {_COLUMNS}"
        ),
        {"id": spray_id, "zone": zone_id},
    ).one_or_none()
    return _spray(row) if row else None
