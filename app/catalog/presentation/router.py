from fastapi import APIRouter, Depends

from app.catalog.application import catalog_service
from app.catalog.domain.entities import PesticideEntry
from app.catalog.presentation.schemas import CropOut, MoaOut, PesticideOut
from app.core.auth import current_user

# 참고 데이터라도 로그인한 사용자만 쓴다 (명세 §1)
router = APIRouter(dependencies=[Depends(current_user)])


def _pesticide_out(entry: PesticideEntry) -> PesticideOut:
    p = entry.pesticide
    moa = MoaOut(label_kr=p.moa.label_kr, system=p.moa.system, code=p.moa.code) if p.moa else None
    return PesticideOut(
        id=p.id,
        name=p.name,
        item_name=p.item_name,
        moa=moa,
        at_planting_only=entry.at_planting_only,
    )


@router.get("/crops", response_model=list[CropOut])
def list_crops():
    return [CropOut(id=c.id, name=c.name) for c in catalog_service.list_crops()]


@router.get("/pesticides", response_model=list[PesticideOut])
def list_pesticides(crop_id: int, pest_id: int | None = None):
    return [_pesticide_out(e) for e in catalog_service.list_pesticides(crop_id, pest_id)]
