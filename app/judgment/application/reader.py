from datetime import date

from sqlalchemy.orm import Session

from app.catalog.application import catalog_service
from app.core.time import KST
from app.judgment.application.service import spray_records
from app.judgment.domain.rules import rotation_summary
from app.judgment.infrastructure import repository
from app.spraying.application import spray_service


def _brief(row) -> dict | None:
    """저장된 판정 한 건을 명세의 JudgmentBrief로 바꾼다. 카탈로그에서 사라진 id면 None."""
    drug = catalog_service.get_pesticide(row.pesticide_id)
    pest = catalog_service.get_pest_card(row.pest_id) if row.pest_id is not None else None
    if drug is None or (row.pest_id is not None and pest is None):
        return None
    return {
        "judgment_id": row.id,
        # 명세 §1: datetime은 KST, 초 단위
        "created_at": row.created_at.astimezone(KST).replace(microsecond=0),
        "pesticide": {"id": drug.id, "name": drug.name, "item_name": drug.item_name},
        "pest": {"id": pest.id, "name": pest.name} if pest else None,
        "verdict": row.verdict,
    }


def recent_judgments(db: Session, zone_id: int, limit: int = 5) -> list[dict]:
    """구역의 최근 판정 (최신순). 호출하는 쪽이 구역 소유자를 확인한다."""
    briefs = (_brief(row) for row in repository.recent(db, zone_id, limit))
    return [brief for brief in briefs if brief is not None]


def last_judgments(db: Session, zone_ids: list[int]) -> dict[int, dict]:
    """구역 id → 가장 최근 판정. 판정이 없거나 그 행이 카탈로그에서 사라진 구역은 빠진다."""
    briefs = {row.zone_id: _brief(row) for row in repository.latest_per_zone(db, zone_ids)}
    return {zone_id: brief for zone_id, brief in briefs.items() if brief is not None}


def rotation(db: Session, zone_id: int, planted_at: date | None) -> dict:
    """구역의 작용기작 편중도 (명세의 Rotation). 정식일이 없으면 전체 기록 기준이다."""
    history = spray_records(spray_service.history(db, zone_id))
    return rotation_summary(history, planted_at).model_dump()
