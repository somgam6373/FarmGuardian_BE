from typing import Annotated

from fastapi import APIRouter, Query

from app.farm.application import field_service
from app.farm.presentation.schemas import Parcel

router = APIRouter()


@router.get("/parcels", response_model=list[Parcel])
def list_parcels(pnu: Annotated[str, Query(pattern=r"^\d{19}$")]):
    return field_service.find_parcels(pnu)
