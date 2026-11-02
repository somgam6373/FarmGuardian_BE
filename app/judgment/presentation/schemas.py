from datetime import date

from pydantic import BaseModel

from app.catalog.presentation.schemas import PesticideDetail, PesticideOut
from app.judgment.domain.schemas import JudgeResult


class JudgmentIn(BaseModel):
    pesticide_id: int
    pest_id: int | None = None
    apply_date: date | None = None


class PreviewItemOut(BaseModel):
    pesticide: PesticideDetail
    at_planting_only: bool
    result: JudgeResult


class JudgeResponse(BaseModel):
    judgment_id: int
    apply_date: date
    pesticide: PesticideOut  # 판정한 약제. 목록 없이도 화면을 그릴 수 있다
    result: JudgeResult
    alternatives: list[PesticideDetail]
    show_extension_office: bool
