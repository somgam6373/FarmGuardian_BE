from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Spray:
    id: int
    pesticide_id: int  # 정적 카탈로그의 약제 id
    sprayed_on: date
    source: str  # 'manual' | 'app'
    pest_id: int | None = None  # 정적 카탈로그의 병해충 id
    cancelled: bool = False
