from datetime import date

from pydantic import BaseModel

from app.catalog.presentation.schemas import PesticideBase
from app.judgment.domain.schemas import JudgeResult


class JudgmentIn(BaseModel):
    pesticide_id: int
    pest_id: int | None = None
    apply_date: date | None = None


class JudgeResponse(BaseModel):
    judgment_id: int
    apply_date: date
    result: JudgeResult
    alternatives: list[PesticideBase]
    show_extension_office: bool
