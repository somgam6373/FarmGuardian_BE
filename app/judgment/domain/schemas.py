from datetime import date
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True)


class Verdict(StrEnum):
    OK = "OK"
    CAUTION = "CAUTION"
    BLOCKED = "BLOCKED"
    NEEDS_CHECK = "NEEDS_CHECK"


class Moa(_Model):
    label_kr: str  # 국내 계열 코드 (예: "라3", 복합제는 "카+가1")
    system: str | None = None  # 국제 코드 (예: "FRAC")
    code: str | None = None  # 국제 코드 번호 (예: "24")


class Registration(_Model):
    # 고른 상표의 이 작물에 대한 등록 행 (사용 방법별)
    pest_id: int
    pest_name: str
    phi_days: int | None
    max_uses: int | None
    use_suittime_raw: str | None
    use_num_raw: str | None
    dilut_raw: str | None
    use_method: str | None
    usage_type: Literal["NORMAL", "AT_PLANTING", "NO_LIMIT", "CHECK"]
    data_asof: date


class SprayRecord(_Model):
    id: int
    pesticide_id: int
    item_name: str
    sprayed_on: date
    moa: Moa | None


class JudgeInput(_Model):
    today: date  # 주입한다. 시계를 읽지 않고 테스트하기 위해서다
    planted_at: date | None
    history_confirmed: bool
    pest_id: int | None
    pesticide_id: int
    item_name: str
    moa: Moa | None
    registrations: list[Registration]
    history: list[SprayRecord]
    psis_asof: date  # 데이터 기준일. 고려할 행이 없을 때 data_asof로 쓴다


class Evidence(_Model):
    source_text: str
    data_asof: date


class CheckResult(_Model):
    key: Literal["registration", "timing", "count", "moa"]
    status: Verdict
    message: str
    facts: dict[str, Any]
    evidence: Evidence


class RotationRule(_Model):
    kind: Literal["NO_LIMIT", "CONSECUTIVE"]
    max_consecutive: int | None  # NO_LIMIT이면 None
    source: str  # 규칙 출처 (rotation_rule.json의 문구)
