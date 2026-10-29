from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.catalog.application import catalog_service
from app.catalog.domain.entities import Moa as CatalogMoa
from app.catalog.domain.entities import Pesticide, UseRow
from app.core.errors import AppError
from app.farm.application import zone_reader
from app.judgment.domain.rules import judge, pick_alternatives
from app.judgment.domain.schemas import (
    JudgeInput,
    JudgeResult,
    Moa,
    Registration,
    SprayRecord,
    Verdict,
)
from app.judgment.infrastructure import repository
from app.spraying.application import spray_service
from app.spraying.application.spray_service import SprayView

NO_ALTERNATIVE_NOTICE = "병해충을 지정하면 대안을 볼 수 있습니다"
# 수확 가능일(오늘 + 수확 전 일수)이 날짜 범위를 넘지 않도록 하는 상한
MAX_APPLY_DATE = date(2100, 12, 31)

# 정적 데이터의 변환 구분을 판정의 사용 유형으로 옮긴다
_USAGE_TYPE = {"ok": "NORMAL", "stage": "AT_PLANTING", "no_std": "NO_LIMIT", "failed": "CHECK"}


@dataclass(frozen=True)
class Assessment:
    result: JudgeResult
    alternatives: list[Pesticide]  # 계열 → 품목명 → 상표명 순
    show_extension_office: bool


def _moa(moa: CatalogMoa | None) -> Moa | None:
    return Moa(label_kr=moa.label_kr, system=moa.system, code=moa.code) if moa else None


def _registration(row: UseRow) -> Registration:
    return Registration(
        pest_id=row.pest_id,
        pest_name=row.pest_name,
        phi_days=row.phi_days,
        max_uses=row.max_uses,
        use_suittime_raw=row.use_time,
        use_num_raw=row.use_count,
        dilut_raw=row.dilution,
        use_method=row.method,
        usage_type=_USAGE_TYPE[row.parse_status],
        data_asof=row.base_date,
    )


def show_extension_office(pest_given: bool, verdict: Verdict, alternative_count: int) -> bool:
    """병해충을 지목했고 불가·주의인데 대안이 없을 때만 농업기술센터 문의를 안내한다."""
    return pest_given and verdict in (Verdict.BLOCKED, Verdict.CAUTION) and alternative_count == 0


def assess(
    *,
    crop_id: int,
    planted_at: date | None,
    history_confirmed: bool,
    history: Sequence[SprayView],
    pesticide_id: int,
    pest_id: int | None,
    today: date,
) -> Assessment:
    """DB 없이 판정과 대안을 만든다. 없는 약제·병해충은 404."""
    chosen = catalog_service.get_pesticide(pesticide_id)
    if chosen is None:
        raise AppError("NOT_FOUND", 404, "약제를 찾을 수 없습니다")
    # 병해충 확인과 후보 풀이 한 번에 나온다 (모르는 병해충·다른 작물의 병해충은 404)
    pool = catalog_service.list_pesticides(crop_id, pest_id) if pest_id is not None else []
    records = [
        SprayRecord(
            id=view.spray.id,
            pesticide_id=view.spray.pesticide_id,
            item_name=view.pesticide.item_name,
            sprayed_on=view.spray.sprayed_on,
            moa=_moa(view.pesticide.moa),
        )
        for view in history
    ]
    asof = catalog_service.data_asof()

    def judged(drug: Pesticide) -> JudgeResult:
        return judge(
            JudgeInput(
                today=today,
                planted_at=planted_at,
                history_confirmed=history_confirmed,
                pest_id=pest_id,
                pesticide_id=drug.id,
                item_name=drug.item_name,
                moa=_moa(drug.moa),
                registrations=[
                    _registration(r) for r in catalog_service.get_registrations(drug.id, crop_id)
                ],
                history=records,
                psis_asof=asof,
            )
        )

    result = judged(chosen)
    others = {e.pesticide.id: e.pesticide for e in pool if e.pesticide.id != chosen.id}
    picked = pick_alternatives(result, [judged(drug) for drug in others.values()])
    alternatives = sorted(
        (others[r.pesticide_id] for r in picked),
        key=lambda drug: (drug.moa.label_kr, drug.item_name, drug.name),
    )
    if pest_id is None and result.verdict is Verdict.BLOCKED:
        result = result.model_copy(update={"notices": [*result.notices, NO_ALTERNATIVE_NOTICE]})
    return Assessment(
        result,
        alternatives,
        show_extension_office(pest_id is not None, result.verdict, len(alternatives)),
    )


@dataclass(frozen=True)
class Judgment:
    id: int
    apply_date: date
    assessment: Assessment


def run_judgment(
    db: Session,
    zone_id: int,
    *,
    pesticide_id: int,
    pest_id: int | None,
    apply_date: date | None,
    today: date,
) -> Judgment:
    """구역의 정보와 이력을 읽어 판정하고 저장한다. 오류면 아무것도 저장하지 않는다."""
    if apply_date is not None and apply_date > MAX_APPLY_DATE:
        message = f"apply_date는 {MAX_APPLY_DATE.isoformat()} 이전이어야 합니다"
        error = {"loc": ["body", "apply_date"], "msg": message, "type": "value_error"}
        raise AppError("VALIDATION_ERROR", 422, message, {"errors": [error]})
    day = apply_date or today
    zone = zone_reader.get_zone_context(db, zone_id)
    assessment = assess(
        crop_id=zone.crop_id,
        planted_at=zone.planted_at,
        history_confirmed=zone.history_confirmed,
        history=spray_service.history(db, zone_id),
        pesticide_id=pesticide_id,
        pest_id=pest_id,
        today=day,
    )
    result = assessment.result
    judgment_id = repository.insert(
        db, zone_id, pest_id, pesticide_id, day, result.verdict.value, result.model_dump_json()
    )
    db.commit()
    return Judgment(judgment_id, day, assessment)
