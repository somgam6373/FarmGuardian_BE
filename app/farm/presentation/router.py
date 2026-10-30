from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from app.core.auth import current_user, get_owned_field, get_owned_zone
from app.core.db import get_db
from app.core.time import today_kst
from app.farm.application import field_service, zone_service
from app.farm.presentation.schemas import (
    AddressSearchResult,
    FieldCreate,
    FieldOut,
    Keyword,
    Parcel,
    SplitPiece,
    SplitRequest,
    ZoneDetail,
    ZoneOut,
    ZonePatch,
    ZonesCreate,
)

router = APIRouter()


def optional_user(
    x_user_id: Annotated[str | None, Header()] = None, db: Session = Depends(get_db)
) -> int | None:
    # 인증 없이 부를 수 있지만, 헤더를 보냈다면 current_user와 같은 규칙으로 확인한다
    return None if x_user_id is None else current_user(x_user_id, db)


@router.get("/parcels", response_model=list[Parcel])
def list_parcels(
    pnu: Annotated[str, Query(pattern=r"^\d{19}$")],
    user_id: Annotated[int | None, Depends(optional_user)],
    db: Session = Depends(get_db),
):
    return field_service.find_parcels(pnu, db, user_id)


@router.get("/addresses/search", response_model=AddressSearchResult)
def search_addresses(
    keyword: Annotated[Keyword, Query()],
    page: Annotated[int, Query(ge=1, le=1000)] = 1,
):
    return field_service.search_addresses(keyword, page)


@router.post("/fields", response_model=FieldOut, status_code=201)
def create_field(
    body: FieldCreate,
    user_id: Annotated[int, Depends(current_user)],
    db: Session = Depends(get_db),
):
    field = field_service.create_field(db, user_id, body.name, body.parcel_farmmap_ids)
    db.commit()
    return field


@router.get("/fields", response_model=list[FieldOut])
def list_fields(user_id: Annotated[int, Depends(current_user)], db: Session = Depends(get_db)):
    return field_service.list_fields(db, user_id)


@router.delete("/fields/{field_id}", status_code=204)
def delete_field(
    field_id: Annotated[int, Depends(get_owned_field)], db: Session = Depends(get_db)
):
    field_service.delete_field(db, field_id)
    db.commit()


@router.post("/fields/{field_id}/split-preview", response_model=list[SplitPiece])
def split_preview(
    body: SplitRequest,
    field_id: Annotated[int, Depends(get_owned_field)],
    db: Session = Depends(get_db),
):
    return field_service.split_preview(db, field_id, body.direction, body.ratios)


@router.post("/fields/{field_id}/zones", response_model=list[ZoneOut], status_code=201)
def create_zones(
    body: ZonesCreate,
    field_id: Annotated[int, Depends(get_owned_field)],
    user_id: Annotated[int, Depends(current_user)],
    db: Session = Depends(get_db),
):
    zones = [zone.model_dump() for zone in body.zones]
    created = field_service.create_zones(
        db, field_id, user_id, body.direction, body.ratios, zones, today_kst()
    )
    db.commit()
    return created


@router.get("/zones/{zone_id}", response_model=ZoneDetail)
def zone_detail(
    zone_id: Annotated[int, Depends(get_owned_zone)], db: Session = Depends(get_db)
):
    return zone_service.zone_detail(db, zone_id)


@router.patch("/zones/{zone_id}", response_model=ZoneOut)
def update_zone(
    body: ZonePatch,
    zone_id: Annotated[int, Depends(get_owned_zone)],
    db: Session = Depends(get_db),
):
    zone = zone_service.update_zone(db, zone_id, body.model_dump(exclude_unset=True), today_kst())
    db.commit()
    return zone
