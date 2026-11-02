from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.catalog.presentation.schemas import PesticideDetail, PestRefOut


class SprayIn(BaseModel):
    pesticide_id: int
    pest_id: int | None = None
    sprayed_on: date | None = None
    source: Literal["manual", "app"]
    request_id: UUID
    allow_duplicate: bool = False


class SprayOut(BaseModel):
    id: int
    pesticide: PesticideDetail
    pest: PestRefOut | None
    sprayed_on: date
    source: Literal["manual", "app"]
    cancelled: bool


class SprayPage(BaseModel):
    total: int
    items: list[SprayOut]
