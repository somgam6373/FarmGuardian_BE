from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.catalog.presentation.schemas import PesticideBase


class SprayIn(BaseModel):
    pesticide_id: int
    sprayed_on: date | None = None
    source: Literal["manual", "app"]
    request_id: UUID
    allow_duplicate: bool = False


class SprayOut(BaseModel):
    id: int
    pesticide: PesticideBase
    sprayed_on: date
    source: Literal["manual", "app"]


class SprayPage(BaseModel):
    total: int
    items: list[SprayOut]
