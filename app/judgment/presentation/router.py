from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.catalog.presentation.schemas import pesticide_base
from app.core.auth import current_user, get_owned_zone
from app.core.db import get_db
from app.core.time import today_kst
from app.judgment.application import service
from app.judgment.presentation.schemas import JudgeResponse, JudgmentIn

router = APIRouter(dependencies=[Depends(current_user)])


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
        result=assessment.result,
        alternatives=[pesticide_base(drug) for drug in assessment.alternatives],
        show_extension_office=assessment.show_extension_office,
    )
