from dataclasses import dataclass


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
