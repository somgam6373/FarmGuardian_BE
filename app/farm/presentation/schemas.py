import re
from typing import Annotated

from pydantic import AfterValidator, BaseModel

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
