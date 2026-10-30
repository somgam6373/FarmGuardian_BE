from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import current_user, get_owned_field
from app.core.db import get_db
from app.farm.application import field_service
from app.farm.presentation.schemas import (
    AddressSearchResult,
    FieldCreate,
    FieldOut,
    Keyword,
    Parcel,
)

router = APIRouter()


@router.get("/parcels", response_model=list[Parcel])
def list_parcels(pnu: Annotated[str, Query(pattern=r"^\d{19}$")]):
    return field_service.find_parcels(pnu)


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
