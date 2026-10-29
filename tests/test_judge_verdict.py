from datetime import date
from itertools import product

import pytest
from pydantic import ValidationError

from app.judgment.domain.rules import overall_verdict
from app.judgment.domain.schemas import PRIORITY, CheckResult, Evidence, JudgeResult, Verdict

KEYS = ["registration", "timing", "count", "moa"]


def check(key, status):
    return CheckResult(
        key=key,
        status=status,
        message="m",
        facts={},
        evidence=Evidence(source_text="없음", data_asof=date(2026, 10, 3)),
    )


def checks(*statuses):
    return [check(key, status) for key, status in zip(KEYS, statuses, strict=True)]


def expected(statuses):  # PRIORITY를 쓰지 않는 독립된 기준
    for status in (Verdict.BLOCKED, Verdict.NEEDS_CHECK, Verdict.CAUTION):
        if status in statuses:
            return status
    return Verdict.OK


def test_priority_order():
    assert PRIORITY == {
        Verdict.BLOCKED: 3,
        Verdict.NEEDS_CHECK: 2,
        Verdict.CAUTION: 1,
        Verdict.OK: 0,
    }


@pytest.mark.parametrize("statuses", list(product(Verdict, repeat=4)))
def test_overall_verdict_is_the_most_severe_status(statuses):
    assert overall_verdict(checks(*statuses)) is expected(statuses)


def result(**overrides):
    base = dict(
        pesticide_id=10,
        moa=None,
        verdict=Verdict.OK,
        checks=checks(*[Verdict.OK] * 4),
        notices=[],
        data_asof=date(2026, 10, 3),
    )
    return JudgeResult(**{**base, **overrides})


def test_judge_result_accepts_four_checks():
    assert len(result().checks) == 4


@pytest.mark.parametrize("n", [0, 3, 5])
def test_judge_result_needs_exactly_four_checks(n):
    with pytest.raises(ValidationError):
        result(checks=[check("registration", Verdict.OK)] * n)
