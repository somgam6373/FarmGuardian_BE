from fastapi import APIRouter, Depends

from app.catalog.application import catalog_service
from app.catalog.domain.entities import PestCard, PesticideEntry
from app.catalog.presentation.schemas import (
    CropOut,
    PestCardOut,
    PesticideOut,
    VectorOut,
    pesticide_base,
)
from app.core.auth import current_user

# 참고 데이터라도 로그인한 사용자만 쓴다 (명세 §1)
router = APIRouter(dependencies=[Depends(current_user)])


def _pesticide_out(entry: PesticideEntry) -> PesticideOut:
    base = pesticide_base(entry.pesticide)
    return PesticideOut(**base.model_dump(), at_planting_only=entry.at_planting_only)


@router.get("/crops", response_model=list[CropOut])
def list_crops():
    return [CropOut(id=c.id, name=c.name) for c in catalog_service.list_crops()]


@router.get("/pesticides", response_model=list[PesticideOut])
def list_pesticides(crop_id: int, pest_id: int | None = None):
    return [_pesticide_out(e) for e in catalog_service.list_pesticides(crop_id, pest_id)]


def _card_out(card: PestCard) -> PestCardOut:
    vectors = [
        VectorOut(id=v.id, name=v.name, guide=v.guide, source=v.source) for v in card.vectors
    ]
    return PestCardOut(
        id=card.id,
        name=card.name,
        kind=card.kind,
        photo_url=card.photo_url,
        photo_source=card.photo_source,
        description=card.description,
        occurrence=card.occurrence,
        occurrence_source=card.occurrence_source,
        vectors=vectors,
    )


@router.get("/crops/{crop_id}/symptom-parts", response_model=list[str])
def list_symptom_parts(crop_id: int):
    return catalog_service.list_symptom_parts(crop_id)


@router.get("/pests/candidates", response_model=list[PestCardOut])
def list_pest_candidates(crop_id: int, part: str):
    return [_card_out(c) for c in catalog_service.list_candidates(crop_id, part)]


@router.get("/pests", response_model=list[PestCardOut])
def list_pests(crop_id: int, q: str | None = None):
    return [_card_out(c) for c in catalog_service.list_pests(crop_id, q)]
