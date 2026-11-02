from typing import Literal

from pydantic import BaseModel

from app.catalog.domain.entities import Pesticide


class CropOut(BaseModel):
    id: int
    name: str


class MoaOut(BaseModel):
    label_kr: str
    system: str | None
    code: str | None


class PesticideBase(BaseModel):
    id: int
    name: str  # 상표명
    item_name: str  # 품목명
    moa: MoaOut | None


class PesticideDetail(PesticideBase):
    company: str | None
    form: str | None
    ingredients: list[str]
    kind: Literal["insecticide", "fungicide", "both"] | None


class PesticideOut(PesticideDetail):
    at_planting_only: bool


def pesticide_base(p: Pesticide) -> PesticideBase:
    moa = MoaOut(label_kr=p.moa.label_kr, system=p.moa.system, code=p.moa.code) if p.moa else None
    return PesticideBase(id=p.id, name=p.name, item_name=p.item_name, moa=moa)


def pesticide_detail(p: Pesticide) -> PesticideDetail:
    return PesticideDetail(
        **pesticide_base(p).model_dump(),
        company=p.company,
        form=p.form,
        ingredients=list(p.ingredients),
        kind=p.kind,
    )


def pesticide_out(p: Pesticide, at_planting_only: bool) -> PesticideOut:
    return PesticideOut(**pesticide_detail(p).model_dump(), at_planting_only=at_planting_only)


class VectorOut(BaseModel):
    id: int
    name: str
    guide: str
    source: str


class PestCardOut(BaseModel):
    id: int
    name: str
    kind: str | None
    photo_url: str | None
    photo_source: str | None
    description: str | None
    occurrence: str | None
    occurrence_source: str | None
    vectors: list[VectorOut]


class LabelReadOut(BaseModel):
    brand: str | None
    product: str | None
    company: str | None
    text: str


class LabelCandidateOut(BaseModel):
    pesticide: PesticideDetail
    score: float


class LabelScanOut(BaseModel):
    candidates: list[LabelCandidateOut]
    read: LabelReadOut
