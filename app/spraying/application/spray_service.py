from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy.orm import Session

from app.catalog.application import catalog_service
from app.catalog.domain.entities import Pesticide
from app.core.errors import AppError
from app.spraying.domain.entities import Spray
from app.spraying.infrastructure import repository


@dataclass(frozen=True)
class SprayView:
    spray: Spray
    pesticide: Pesticide


class DuplicateSpray(Exception):
    def __init__(self, existing: SprayView):
        super().__init__("duplicate spray")
        self.existing = existing


def _invalid(field: str, message: str) -> AppError:
    # 보낸 값은 메시지에 넣지 않는다
    error = {"loc": ["body", field], "msg": message, "type": "value_error"}
    return AppError("VALIDATION_ERROR", 422, message, {"errors": [error]})


def _view(spray: Spray) -> SprayView:
    return SprayView(spray, catalog_service.get_pesticide(spray.pesticide_id))


def _replay(db: Session, zone_id: int, request_id: UUID) -> SprayView | None:
    found = repository.find_by_request_id(db, request_id)
    if found is None:
        return None
    spray, owner_zone_id = found
    if owner_zone_id != zone_id:  # 다른 구역·다른 사용자의 기록은 보여주지 않는다
        raise _invalid("request_id", "이미 사용된 request_id입니다")
    return _view(spray)


def record_spray(
    db: Session,
    zone_id: int,
    *,
    pesticide_id: int,
    sprayed_on: date | None,
    source: str,
    request_id: UUID,
    allow_duplicate: bool,
    today: date,
) -> tuple[SprayView, bool]:
    """저장한 기록과 새로 저장했는지 여부. 재시도면 (원본, False)."""
    if catalog_service.get_pesticide(pesticide_id) is None:
        raise _invalid("pesticide_id", "알 수 없는 약제입니다")
    sprayed_on = sprayed_on or today
    if sprayed_on > today:
        raise _invalid("sprayed_on", "미래 날짜는 기록할 수 없습니다")
    replayed = _replay(db, zone_id, request_id)
    if replayed:
        return replayed, False
    if not allow_duplicate:
        existing = repository.find_duplicate(db, zone_id, pesticide_id, sprayed_on)
        if existing:
            # 원본과 동시에 도착한 재시도는 방금 저장된 원본을 중복으로 보게 된다
            replayed = _replay(db, zone_id, request_id)
            if replayed:
                return replayed, False
            raise DuplicateSpray(_view(existing))
    saved = repository.insert(db, zone_id, pesticide_id, sprayed_on, source, request_id)
    if saved is None:  # 같은 request_id가 그 사이에 저장됐다
        return _replay(db, zone_id, request_id), False
    db.commit()
    return _view(saved), True


def list_sprays(
    db: Session, zone_id: int, limit: int = 20, offset: int = 0
) -> tuple[int, list[SprayView]]:
    total, sprays = repository.page(db, zone_id, limit, offset)
    return total, [_view(spray) for spray in sprays]


def history(db: Session, zone_id: int) -> list[SprayView]:
    """판정 입력용: 구역의 살포 기록 전체, 최근순."""
    return [_view(spray) for spray in repository.all_for_zone(db, zone_id)]


def cancel_spray(db: Session, zone_id: int, spray_id: int) -> None:
    if not repository.delete(db, zone_id, spray_id):
        raise AppError("NOT_FOUND", 404, "찾을 수 없습니다")
    db.commit()
