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
