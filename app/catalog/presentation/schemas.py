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
