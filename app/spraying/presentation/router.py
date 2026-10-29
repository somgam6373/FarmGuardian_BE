from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.catalog.presentation.schemas import pesticide_base
from app.core.auth import current_user, get_owned_zone
from app.core.db import get_db
from app.core.errors import AppError
from app.core.time import today_kst
from app.spraying.application import spray_service
from app.spraying.application.spray_service import DuplicateSpray, SprayView
from app.spraying.presentation.schemas import SprayIn, SprayOut, SprayPage

router = APIRouter(dependencies=[Depends(current_user)])

OwnedZone = Annotated[int, Depends(get_owned_zone)]


def _spray_out(view: SprayView) -> SprayOut:
    spray = view.spray
    return SprayOut(
        id=spray.id,
        pesticide=pesticide_base(view.pesticide),
        sprayed_on=spray.sprayed_on,
        source=spray.source,
    )


@router.post("/zones/{zone_id}/sprays", response_model=SprayOut, status_code=201)
def create_spray(
    body: SprayIn, response: Response, zone_id: OwnedZone, db: Session = Depends(get_db)
):
    try:
        view, created = spray_service.record_spray(
            db,
            zone_id,
            pesticide_id=body.pesticide_id,
            sprayed_on=body.sprayed_on,
            source=body.source,
            request_id=body.request_id,
            allow_duplicate=body.allow_duplicate,
            today=today_kst(),
        )
    except DuplicateSpray as duplicate:
        existing = _spray_out(duplicate.existing).model_dump(mode="json")
        message = "같은 구역·약제·날짜의 기록이 이미 있습니다"
        raise AppError("DUPLICATE_SPRAY", 409, message, {"existing": existing}) from None
    if not created:  # 재시도: 저장하지 않고 원본을 돌려준다
        response.status_code = 200
    return _spray_out(view)


@router.get("/zones/{zone_id}/sprays", response_model=SprayPage)
def list_sprays(
    zone_id: OwnedZone,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
):
    total, views = spray_service.list_sprays(db, zone_id, limit, offset)
    return SprayPage(total=total, items=[_spray_out(v) for v in views])


@router.delete("/zones/{zone_id}/sprays/{spray_id}", status_code=204)
def cancel_spray(zone_id: OwnedZone, spray_id: int, db: Session = Depends(get_db)):
    spray_service.cancel_spray(db, zone_id, spray_id)
