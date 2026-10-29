from datetime import date

import pytest

from app.judgment.domain.rules import judge
from app.judgment.domain.schemas import Moa, Verdict
from tests.judge_support import make_input, recent, reg

OK, CAUTION, NEEDS_CHECK, BLOCKED = (
    Verdict.OK,
    Verdict.CAUTION,
    Verdict.NEEDS_CHECK,
    Verdict.BLOCKED,
)
KEYS = ["registration", "timing", "count", "moa"]
NOTICE = "병해충을 지정하지 않아 가장 엄격한 기준을 적용했습니다"
FORBIDDEN = ["추천", "예측", "예상", "가능성", "위험", "확률", "안전", "문제없"]
OTHER = dict(pest_id=2, pest_name="역병")


def run(**kw):
    return judge(make_input(**kw))


def test_v1_registration_blocked_wins_although_action_group_is_independent():
    r = run(registrations=[], history=recent("가1", "가1"))

    assert r.verdict is BLOCKED
    assert (r.checks[0].status, r.checks[3].status) == (BLOCKED, CAUTION)


def test_v2_needs_check_beats_caution():
    r = run(planted_at=None, history=recent("가1", "가1"))

    assert (r.checks[2].status, r.checks[3].status) == (NEEDS_CHECK, CAUTION)
    assert r.verdict is NEEDS_CHECK


def test_v3_caution_alone():
    r = run(history=recent("가1", "가1"))

    assert [c.status for c in r.checks] == [OK, OK, OK, CAUTION]
    assert r.verdict is CAUTION


def test_v4_all_ok_with_four_checks_in_order():
    r = run()

    assert r.verdict is OK
    assert [c.key for c in r.checks] == KEYS
    assert all(c.status is OK for c in r.checks)
    assert r.notices == []


def test_v5_data_asof_is_the_oldest_considered_row():
    rows = [
        reg(data_asof=date(2026, 10, 1)),
        reg(data_asof=date(2026, 9, 20), use_method="무인항공"),
    ]

    assert run(registrations=rows).data_asof == date(2026, 9, 20)


@pytest.mark.parametrize(
    "kw",
    [{}, {"registrations": [reg(**OTHER)]}, {"registrations": []}, {"moa": None}],
    ids=["base", "R2", "R3", "M6"],
)
def test_v6_every_check_has_evidence_with_the_result_date(kw):
    r = run(**kw)

    assert len(r.checks) == 4
    for c in r.checks:
        assert c.evidence.source_text
        assert c.evidence.data_asof == r.data_asof


def test_v7_no_pest_is_needs_check():
    assert run(pest_id=None).verdict is NEEDS_CHECK


def test_r2_only_other_pests_registered_is_blocked_without_notice():
    r = run(registrations=[reg(**OTHER)])

    assert r.verdict is BLOCKED
    assert r.notices == []


def test_r4_no_pest_gets_the_notice():
    r = run(pest_id=None)

    assert (r.verdict, r.notices) == (NEEDS_CHECK, [NOTICE])


def test_r5_no_pest_and_nothing_registered_has_no_notice():
    r = run(pest_id=None, registrations=[])

    assert (r.verdict, r.notices) == (BLOCKED, [])


def test_without_considered_rows_the_result_date_is_the_input_date():
    assert run(registrations=[]).data_asof == date(2026, 10, 3)


def test_pesticide_and_moa_are_copied_from_the_input():
    r = run()

    assert r.pesticide_id == 10
    assert r.moa == Moa(label_kr="가1", system="FRAC", code="4")
    assert run(moa=None).moa is None


def test_serializes_to_the_spec_shape():
    data = run().model_dump(mode="json")

    assert list(data) == ["pesticide_id", "moa", "verdict", "checks", "notices", "data_asof"]
    assert data["moa"] == {"label_kr": "가1", "system": "FRAC", "code": "4"}
    assert (data["verdict"], data["data_asof"]) == ("OK", "2026-10-01")
    assert [c["key"] for c in data["checks"]] == KEYS
    assert all(set(c) == {"key", "status", "message", "facts", "evidence"} for c in data["checks"])
    assert data["checks"][1]["facts"]["harvest_from"] == "2026-10-11"
    assert data["checks"][3]["evidence"]["data_asof"] == "2026-10-01"
    assert run(moa=None).model_dump(mode="json")["moa"] is None


def test_judge_is_pure():
    inp = make_input(history=recent("가1", "나2"))
    before = inp.model_dump()

    first = judge(inp)

    assert inp.model_dump() == before
    assert judge(inp) == first


def test_notice_has_no_forbidden_word():
    assert not [w for w in FORBIDDEN if w in NOTICE]
