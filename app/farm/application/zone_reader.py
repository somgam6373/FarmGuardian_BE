from dataclasses import dataclass
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import AppError


@dataclass(frozen=True)
class ZoneContext:
    crop_id: int
    planted_at: date | None
    history_confirmed: bool  # 「누락 없음」 확인


def get_zone_context(db: Session, zone_id: int) -> ZoneContext:
    row = db.execute(
        text("SELECT crop_id, planted_at, history_confirmed FROM zone WHERE id = :id"),
        {"id": zone_id},
    ).one_or_none()
    if row is None:
        raise AppError("NOT_FOUND", 404, "찾을 수 없습니다")
    return ZoneContext(row.crop_id, row.planted_at, row.history_confirmed)


@dataclass(frozen=True)
class ZoneState:
    id: int
    history_confirmed: bool


def list_user_zones(db: Session, user_id: int) -> list[ZoneState]:
    """사용자의 구역 전부 (id 순). 온보딩이 구역 수와 「누락 없음」 상태를 본다."""
    rows = db.execute(
        text("SELECT id, history_confirmed FROM zone WHERE user_id = :uid ORDER BY id"),
        {"uid": user_id},
    ).all()
    return [ZoneState(row.id, row.history_confirmed) for row in rows]
