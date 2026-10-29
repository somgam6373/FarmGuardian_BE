from datetime import date

from app.judgment.domain.rules import check_registration
from app.judgment.domain.schemas import Verdict
from tests.judge_support import make_input, reg

OTHER = dict(pest_id=2, pest_name="역병")


def run(**kw):
    return check_registration(make_input(**kw))


def test_r1_registered_for_the_pest():
    r = run()

    assert (r.key, r.status) == ("registration", Verdict.OK)
    assert r.message == "이 병해충에 등록된 약제입니다"
    assert r.facts == {"pest_specified": True, "rows": 1}
    assert r.evidence.source_text == "발생 초부터 경엽처리 · 1000배"
    assert r.evidence.data_asof == date(2026, 10, 1)


def test_r2_only_other_pests_registered():
    r = run(registrations=[reg(**OTHER)])

    assert r.status is Verdict.BLOCKED
    assert r.message == "이 병해충에는 등록되어 있지 않습니다 (이 작물에 등록된 병해충 1종)"
    assert r.facts == {"crop_registered": True, "registered_pests": ["역병"]}
    assert r.evidence.source_text == "등록 병해충: 역병"
    assert r.evidence.data_asof == date(2026, 10, 3)


def test_r3_nothing_registered_for_the_crop():
    r = run(registrations=[])

    assert r.status is Verdict.BLOCKED
    assert r.message == "이 작물에는 등록되어 있지 않습니다"
    assert r.facts == {"crop_registered": False}
    assert r.evidence.source_text == "없음"
    assert r.evidence.data_asof == date(2026, 10, 3)


def test_r4_pest_not_specified():
    r = run(pest_id=None)

    assert r.status is Verdict.NEEDS_CHECK
    assert r.message == (
        "병해충을 지정하지 않아 등록 여부를 확인할 수 없습니다 (이 작물에는 등록되어 있습니다)"
    )
    assert r.facts == {
        "crop_registered": True,
        "pest_specified": False,
        "registered_pests": ["탄저병"],
    }
    assert r.evidence.source_text == "등록 병해충: 탄저병"


def test_r5_pest_not_specified_and_nothing_registered():
    r = run(pest_id=None, registrations=[])

    assert r.status is Verdict.BLOCKED
    assert r.facts == {"crop_registered": False}


def test_r6_registered_pests_are_distinct_and_sorted():
    rows = [
        reg(**OTHER),
        reg(**OTHER, use_method="토양처리"),
        reg(pest_id=3, pest_name="겹둥근무늬병"),
    ]
    r = run(registrations=rows)

    assert r.message.endswith("(이 작물에 등록된 병해충 2종)")
    assert r.facts["registered_pests"] == ["겹둥근무늬병", "역병"]
    assert r.evidence.source_text == "등록 병해충: 겹둥근무늬병, 역병"


def test_r7_evidence_shows_only_what_exists():
    both_empty = run(registrations=[reg(use_method=None, dilut_raw=None)])
    no_method = run(registrations=[reg(use_method=None)])
    no_dilution = run(registrations=[reg(dilut_raw=None)])

    assert both_empty.evidence.source_text == "없음"
    assert no_method.evidence.source_text == "1000배"
    assert no_dilution.evidence.source_text == "발생 초부터 경엽처리"


def test_rows_counts_considered_rows_and_data_asof_ignores_other_pests():
    rows = [
        reg(data_asof=date(2026, 10, 1)),
        reg(data_asof=date(2026, 9, 20), use_method="무인항공"),
        reg(**OTHER, data_asof=date(2026, 1, 1)),
    ]
    r = run(registrations=rows)

    assert r.facts == {"pest_specified": True, "rows": 2}
    assert r.evidence.data_asof == date(2026, 9, 20)
    assert r.evidence.source_text == "발생 초부터 경엽처리 · 1000배"  # 입력 순서의 첫 행
