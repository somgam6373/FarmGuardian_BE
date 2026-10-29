from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Crop:
    id: int
    name: str


@dataclass(frozen=True)
class Moa:
    label_kr: str  # 국내 계열 코드 (복합제는 '카+가1')
    system: str | None  # 국제 코드의 체계 (예: 'FRAC'). 모르면 None
    code: str | None  # 국제 코드 번호 (예: '4'). 모르면 None


@dataclass(frozen=True)
class Pesticide:
    id: int
    name: str  # 상표명
    item_name: str  # 품목명
    moa: Moa | None


@dataclass(frozen=True)
class PesticideEntry:
    pesticide: Pesticide
    at_planting_only: bool  # 이 작물(·병해충)의 등록 행이 모두 「심을 때」 사용


@dataclass(frozen=True)
class UseRow:
    # 약제의 등록 행 하나 (사용 방법별). 판정 입력의 원재료다
    pest_id: int
    pest_name: str
    phi_days: int | None
    max_uses: int | None
    use_time: str | None  # 원문
    use_count: str | None  # 원문
    dilution: str | None  # 원문
    method: str | None  # 사용 방법 원문
    parse_status: str  # 'ok' | 'stage' | 'no_std' | 'failed'
    base_date: date  # 데이터 기준일


@dataclass(frozen=True)
class PestVector:
    id: int  # 매개충의 병해충 id
    name: str
    guide: str  # 앱 안내 문구
    source: str  # 근거


@dataclass(frozen=True)
class PestCard:
    id: int
    name: str
    kind: str | None  # '병' | '해충'
    photo_url: str | None
    photo_source: str | None  # 사진 출처 (작물명, '양배추(대체)' 등)
    description: str | None  # 증상·피해
    occurrence: str | None  # 발생 시기 (월 + 근거)
    occurrence_source: str | None
    vectors: tuple[PestVector, ...]
