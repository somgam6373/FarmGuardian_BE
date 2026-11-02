from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.catalog.presentation.schemas import pesticide_detail, pesticide_out
from app.core.auth import current_user, get_owned_zone
from app.core.db import get_db
from app.core.time import today_kst
from app.judgment.application import service
from app.judgment.presentation.schemas import JudgeResponse, JudgmentIn, PreviewItemOut

router = APIRouter(dependencies=[Depends(current_user)])


@router.get("/zones/{zone_id}/judgments/preview", response_model=list[PreviewItemOut])
def preview_judgments(
    zone_id: Annotated[int, Depends(get_owned_zone)],
    pest_id: int,
    apply_date: date | None = None,
    db: Session = Depends(get_db),
):
    """저장하지 않는 일괄 판정: 이 구역·병해충에 등록된 약제 전부."""
    items = service.preview(
        db, zone_id, pest_id=pest_id, apply_date=apply_date, today=today_kst()
    )
    return [
        PreviewItemOut(
            pesticide=pesticide_detail(item.entry.pesticide),
            at_planting_only=item.entry.at_planting_only,
            result=item.result,
        )
        for item in items
    ]


@router.post("/zones/{zone_id}/judgments", response_model=JudgeResponse, status_code=201)
def create_judgment(
    body: JudgmentIn,
    zone_id: Annotated[int, Depends(get_owned_zone)],
    db: Session = Depends(get_db),
):
    judgment = service.run_judgment(
        db,
        zone_id,
        pesticide_id=body.pesticide_id,
        pest_id=body.pest_id,
        apply_date=body.apply_date,
        today=today_kst(),
    )
    assessment = judgment.assessment
    return JudgeResponse(
        judgment_id=judgment.id,
        apply_date=judgment.apply_date,
        pesticide=pesticide_out(assessment.pesticide, assessment.at_planting_only),
        result=assessment.result,
        alternatives=[pesticide_detail(drug) for drug in assessment.alternatives],
        show_extension_office=assessment.show_extension_office,
    )
