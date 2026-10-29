from pydantic import BaseModel


class CropOut(BaseModel):
    id: int
    name: str


class MoaOut(BaseModel):
    label_kr: str
    system: str | None
    code: str | None


class PesticideOut(BaseModel):
    id: int
    name: str  # 상표명
    item_name: str  # 품목명
    moa: MoaOut | None
    at_planting_only: bool


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
