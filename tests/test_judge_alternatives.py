from datetime import date

import pytest

from app.judgment.domain.rules import pick_alternatives
from app.judgment.domain.schemas import CheckResult, Evidence, JudgeResult, Moa, Verdict

OK = Verdict.OK


def jr(verdict, label, system=None, code=None, pesticide_id=1):
    moa = None if label is None else Moa(label_kr=label, system=system, code=code)
    checks = [
        CheckResult(
            key=key,
            status=verdict,
            message="m",
            facts={},
            evidence=Evidence(source_text="없음", data_asof=date(2026, 10, 3)),
        )
        for key in ("registration", "timing", "count", "moa")
    ]
    return JudgeResult(
        pesticide_id=pesticide_id,
        moa=moa,
        verdict=verdict,
        checks=checks,
        notices=[],
        data_asof=date(2026, 10, 3),
    )


SELECTED = jr(Verdict.BLOCKED, "가1", "FRAC", "4", pesticide_id=10)


def test_a1_other_group_is_kept():
    other = jr(OK, "나2", pesticide_id=11)

    assert pick_alternatives(SELECTED, [other]) == [other]


def test_a2_same_group_is_dropped():
    assert pick_alternatives(SELECTED, [jr(OK, "가1", pesticide_id=11)]) == []


@pytest.mark.parametrize("verdict", [Verdict.CAUTION, Verdict.BLOCKED, Verdict.NEEDS_CHECK])
def test_a3_not_ok_is_dropped(verdict):
    assert pick_alternatives(SELECTED, [jr(verdict, "나2", pesticide_id=11)]) == []


def test_a4_ok_without_moa_is_dropped():
    assert pick_alternatives(SELECTED, [jr(OK, None, pesticide_id=11)]) == []


def test_a5_selected_without_moa_skips_only_the_group_comparison():
    selected = jr(Verdict.BLOCKED, None, pesticide_id=10)
    with_moa = jr(OK, "나2", pesticide_id=11)
    without_moa = jr(OK, None, pesticide_id=12)

    assert pick_alternatives(selected, [with_moa, without_moa]) == [with_moa]


def test_same_label_with_another_system_is_dropped():
    assert pick_alternatives(SELECTED, [jr(OK, "가1", "IRAC", "4", pesticide_id=11)]) == []


def test_kept_items_stay_in_input_order_and_are_the_same_objects():
    others = [
        jr(OK, "나2", pesticide_id=11),
        jr(OK, "다3", pesticide_id=12),
        jr(OK, "가1", pesticide_id=13),
        jr(Verdict.CAUTION, "라3", pesticide_id=14),
        jr(OK, "나2", pesticide_id=15),
    ]
    result = pick_alternatives(SELECTED, others)

    assert [r.pesticide_id for r in result] == [11, 12, 15]
    assert result[0] is others[0] and result[2] is others[4]


def test_no_candidates():
    assert pick_alternatives(SELECTED, []) == []
