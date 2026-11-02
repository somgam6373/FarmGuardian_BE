from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile

from app.catalog.application import catalog_service, label_service
from app.catalog.domain.entities import PestCard
from app.catalog.presentation.schemas import (
    CropOut,
    LabelCandidateOut,
    LabelReadOut,
    LabelScanOut,
    PestCardOut,
    PesticideOut,
    PestRefOut,
    VectorOut,
    pesticide_detail,
    pesticide_out,
)
from app.catalog.presentation.upload import read_image
from app.core.auth import current_user

# 참고 데이터라도 로그인한 사용자만 쓴다 (명세 §1)
router = APIRouter(dependencies=[Depends(current_user)])


@router.get("/crops", response_model=list[CropOut])
def list_crops():
    return [CropOut(id=c.id, name=c.name) for c in catalog_service.list_crops()]


@router.get("/pesticides", response_model=list[PesticideOut])
def list_pesticides(crop_id: int, pest_id: int | None = None):
    entries = catalog_service.list_pesticides(crop_id, pest_id)
    return [pesticide_out(e.pesticide, e.at_planting_only) for e in entries]


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
        months=list(card.months),
        pesticide_count=card.pesticide_count,
        is_virus=card.is_virus,
        carries=[PestRefOut(id=ref.id, name=ref.name) for ref in card.carries],
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


@router.post("/ocr/pesticide-labels", response_model=LabelScanOut)
def scan_pesticide_label(image: Annotated[UploadFile, File()]):
    data, media_type = read_image(image)
    scan = label_service.scan_label(data, media_type)
    return LabelScanOut(
        candidates=[
            LabelCandidateOut(
                pesticide=pesticide_detail(c.pesticide), score=c.score, matched=list(c.matched)
            )
            for c in scan.candidates
        ],
        read=LabelReadOut(**asdict(scan.read)),
    )
