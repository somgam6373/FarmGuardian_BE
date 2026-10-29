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


class PesticideOut(PesticideBase):
    at_planting_only: bool


def pesticide_base(p: Pesticide) -> PesticideBase:
    moa = MoaOut(label_kr=p.moa.label_kr, system=p.moa.system, code=p.moa.code) if p.moa else None
    return PesticideBase(id=p.id, name=p.name, item_name=p.item_name, moa=moa)


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
