import re
from datetime import date
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, StringConstraints

from app.catalog.presentation.schemas import CropOut, PesticideBase

# 브이월드 방화벽이 따옴표·<> 등을 막으므로 지번 입력에 필요한 글자만 받는다
KEYWORD_PATTERN = re.compile(r"[가-힣0-9 \-]{2,80}")


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


def check_keyword(value: str) -> str:
    keyword = value.strip()
    if not KEYWORD_PATTERN.fullmatch(keyword):
        raise ValueError("검색어는 한글·숫자·공백·하이픈 2~80자여야 합니다")
    # 숫자만으로는 전국 지번이 다 걸리므로 리·동 이름을 요구한다
    if not re.search(r"[가-힣]", keyword):
        raise ValueError("검색어에 리·동 이름이 있어야 합니다")
    return keyword


Keyword = Annotated[str, AfterValidator(check_keyword)]


class AddressItem(BaseModel):
    jibun_addr: str
    pnu: str


class AddressSearchResult(BaseModel):
    total: int
    items: list[AddressItem]


# 빈 번호는 팜맵이 오류 코드 11(→ 502)로 답하므로 호출 전에 막는다.
# \d는 전각 숫자도 받으므로 ASCII 숫자만 쓴다
FarmmapId = Annotated[str, StringConstraints(pattern=r"^[0-9]{1,30}$")]


def check_unique(ids: list[str]) -> list[str]:
    if len(set(ids)) != len(ids):
        raise ValueError("필지 번호가 중복되었습니다")
    return ids


class FieldCreate(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]
    parcel_farmmap_ids: Annotated[
        list[FarmmapId], Field(min_length=1, max_length=20), AfterValidator(check_unique)
    ]


class LastSpray(BaseModel):
    id: int
    pesticide: PesticideBase
    sprayed_on: date
    source: Literal["manual", "app"]


class ZoneSummary(BaseModel):
    id: int
    name: str
    crop: CropOut
    planted_at: date | None
    history_confirmed: bool
    area_m2: float
    geometry: dict
    last_spray: LastSpray | None
    last_judgment: dict | None  # 판정 조회 서비스가 생길 때까지 항상 null


class FieldOut(BaseModel):
    id: int
    name: str
    area_m2: float
    geometry: dict
    bbox: list[float]
    zones: list[ZoneSummary]
