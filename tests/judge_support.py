from datetime import date, timedelta

from app.judgment.domain.schemas import JudgeInput, Moa, Registration, SprayRecord

TODAY = date(2026, 10, 4)


def reg(**overrides) -> Registration:
    """판정 규칙 §9의 base 등록 행. overrides로 값을 바꾼다."""
    base = dict(
        pest_id=1,
        pest_name="탄저병",
        phi_days=7,
        max_uses=3,
        use_suittime_raw="수확 7일 전까지",
        use_num_raw="3회 이내",
        dilut_raw="1000배",
        use_method="발생 초부터 경엽처리",
        usage_type="NORMAL",
        data_asof=date(2026, 10, 1),
    )
    return Registration(**{**base, **overrides})


def make_input(**overrides) -> JudgeInput:
    """판정 규칙 §9의 base 입력. overrides로 값을 바꾼다."""
    base = dict(
        today=TODAY,
        planted_at=date(2026, 5, 1),
        history_confirmed=True,
        pest_id=1,
        pesticide_id=10,
        item_name="품목A",
        moa=Moa(label_kr="가1", system="FRAC", code="4"),
        registrations=[reg()],
        history=[],
        psis_asof=date(2026, 10, 3),
    )
    return JudgeInput(**{**base, **overrides})


def spray(
    sid: int,
    label: str | None,
    on: date,
    item_name: str = "품목A",
    pesticide_id: int = 10,
) -> SprayRecord:
    """살포 이력 1건. label이 None이면 작용기작 미상."""
    moa = None if label is None else Moa(label_kr=label)
    return SprayRecord(
        id=sid, pesticide_id=pesticide_id, item_name=item_name, sprayed_on=on, moa=moa
    )


def recent(*labels: str | None) -> list[SprayRecord]:
    """labels는 최근순. 가장 최근이 2026-09-01이고 하루씩 앞선다. 오래된 것부터 돌려준다."""
    records = [
        spray(len(labels) - i, label, date(2026, 9, 1) - timedelta(days=i))
        for i, label in enumerate(labels)
    ]
    return records[::-1]
