from typing import Annotated

from fastapi import APIRouter, Query

from app.farm.application import field_service
from app.farm.presentation.schemas import AddressSearchResult, Keyword, Parcel

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
