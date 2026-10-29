from pydantic import BaseModel


class Parcel(BaseModel):
    farmmap_id: str
    pnu: str
    lnm: str
    land_use: str
    vdpt_yr: int | None
    area_m2: float
    geometry: dict
    matches_query: bool
    used_by_field_id: int | None
