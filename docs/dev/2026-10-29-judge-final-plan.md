# Judgment Overall Result `judge()` Implementation Plan (BE-42)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (project CLAUDE.md: no subagent-driven execution). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `judge(inp) -> JudgeResult` that joins the four checks into the spec's `JudgeResult` (overall verdict, notices, data date), plus the `overall_verdict` helper and the `JudgeResult` type.

**Architecture:** `PRIORITY` and `JudgeResult` in `app/judgment/domain/schemas.py`; `overall_verdict` and `judge` in `rules.py`, composed from the existing `check_registration`, `check_timing`, `check_count`, `check_moa` and `rows_data_asof`.

**Tech Stack:** Python 3.13, Pydantic v2, pytest.

**Spec:** `docs/dev/2026-10-29-judge-final-design.md` (approved in chat 2026-10-29); rules in `docs/dev/팜가디언_판정_규칙.md` §2, §5, §9; frame = `docs/dev/팜가디언_API_명세.md` (never edited).

## Global Constraints

- `팜가디언_API_명세.md` is the frame and **must not change**: no commit of this plan touches it.
- `JudgeResult` fields, in this order: `pesticide_id: int`, `moa: Moa | None`, `verdict: Verdict`, `checks: list[CheckResult]` (exactly 4), `notices: list[str]`, `data_asof: date`. Serialized with `model_dump(mode="json")` it has those six keys and ISO date strings.
- `PRIORITY = {BLOCKED: 3, NEEDS_CHECK: 2, CAUTION: 1, OK: 0}`.
- The only notice `judge()` produces is 「병해충을 지정하지 않아 가장 엄격한 기준을 적용했습니다」, when `pest_id` is None and `registrations` is not empty. The service notice 「병해충을 지정하면 대안을 볼 수 있습니다」 is not added here (BE-45).
- `app/judgment/domain/` imports no `sqlalchemy`, `fastapi`, `httpx` and never reads the clock (the existing guard test covers the new code).
- Code and identifiers in English, short Korean comments as in `app/core`; ruff line length 100 (Korean characters count double, wrap long strings); tests flat in `tests/`; commit messages in English; do not push.

## Review Focus

- ④ does not depend on ①: with nothing registered the verdict is `BLOCKED` while ④ still reports `CAUTION`. (Task 2, V1)
- The notice appears only when there are registrations to take the strictest value from: not for R5, not when a pest is chosen. (Task 2, R2/R4/R5)
- Every one of the 256 status combinations aggregates to the most severe status, checked against an oracle that does not use `PRIORITY`. (Task 1)
- `data_asof` of the result equals `evidence.data_asof` of all four checks, also when no registration row is considered (`psis_asof`). (Task 2, V6)
- `checks` of any length other than four is rejected by the type. (Task 1)

---

### Task 0: Commit the design and this plan

- [ ] **Step 1:** `git add docs/dev/2026-10-29-judge-final-design.md docs/dev/2026-10-29-judge-final-plan.md` / `git commit -m "Add judgment overall result design and plan"`

### Task 1: Types and `overall_verdict`

**Files:**
- Modify: `app/judgment/domain/schemas.py`, `app/judgment/domain/rules.py`
- Test: `tests/test_judge_verdict.py`

**Interfaces:**
- Produces in `schemas.py`: `PRIORITY: dict[Verdict, int]` and `JudgeResult(pesticide_id: int, moa: Moa | None, verdict: Verdict, checks: list[CheckResult] = Field(min_length=4, max_length=4), notices: list[str], data_asof: date)` (frozen like the other models, fields in this order).
- Produces in `rules.py`: `overall_verdict(checks: Sequence[CheckResult]) -> Verdict` — the status with the highest `PRIORITY`.

- [ ] **Step 1: Write the failing tests** in `tests/test_judge_verdict.py`
```python
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
```
- [ ] **Step 2: Run** `.venv\Scripts\python -m pytest tests\test_judge_verdict.py -q` — Expected: collection ERROR `cannot import name 'overall_verdict'`.
- [ ] **Step 3: Implement** `PRIORITY` and `JudgeResult` in `schemas.py` and `overall_verdict` in `rules.py` per the interface block.
- [ ] **Step 4: Run** the step 2 command — Expected: `261 passed` (1 order + 256 combinations + 1 accepts + 3 rejections). Full suite and `ruff check .` clean.
- [ ] **Step 5: Commit** `git add app/judgment tests/test_judge_verdict.py` / `git commit -m "Add judgment result type and overall verdict"`

### Task 2: `judge()`

**Files:**
- Modify: `app/judgment/domain/rules.py`
- Test: `tests/test_judge_result.py`

**Interfaces:**
- Consumes: Task 1, the four `check_*` functions, `rows_data_asof`.
- Produces: `judge(inp: JudgeInput) -> JudgeResult`: `registration = check_registration(inp)`, then `check_timing(inp, registration)`, `check_count(inp, registration)`, `check_moa(inp)` in that order as `checks`; `verdict = overall_verdict(checks)`; `notices` per the constraint above; `data_asof = rows_data_asof(inp)`; `pesticide_id` and `moa` copied from `inp`. Keep the notice text as a module constant.

- [ ] **Step 1: Write the failing tests** in `tests/test_judge_result.py`
```python
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
    rows = [reg(data_asof=date(2026, 10, 1)), reg(data_asof=date(2026, 9, 20), use_method="무인항공")]

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
```
- [ ] **Step 2: Run** `.venv\Scripts\python -m pytest tests\test_judge_result.py -q` — Expected: collection ERROR `cannot import name 'judge'`.
- [ ] **Step 3: Implement `judge`** in `rules.py` per the interface block.
- [ ] **Step 4: Run** the step 2 command — Expected: `18 passed` (V1–V5 five, V6 four, V7, R2/R4/R5 three, plus date, copy, shape, purity and notice-scan tests). Full suite and `ruff check .` clean (wrap long lines).
- [ ] **Step 5: Commit** `git add app/judgment/domain/rules.py tests/test_judge_result.py` / `git commit -m "Add judge overall result"`
- [ ] **Step 6: Mutation check.** In `judge` change the notice condition to ignore `registrations` (notice whenever `pest_id` is None), run `tests\test_judge_result.py` — Expected: `test_r5_no_pest_and_nothing_registered_has_no_notice` FAILS; restore with `git checkout -- app/judgment/domain/rules.py`; re-run — `18 passed`; `git status --short` clean.

### Task 3: Final verification

- [ ] **Step 1:** `.venv\Scripts\python -m pytest -q -rs` and `.venv\Scripts\ruff check .` — Expected: all pass, `All checks passed!`.
- [ ] **Step 2:** `git diff --name-only origin/test..HEAD` lists no `팜가디언_API_명세.md`; `git status -sb` clean; `git log --oneline origin/test..HEAD` shows 3 commits. Do not push.
- [ ] **Step 3:** Tell the user: the judgment domain is complete (④ checks, `judge()`); open for BE-43 (`rotation_summary`), BE-44 (`pick_alternatives`), BE-45 (conversion from static rows, service notice, `show_extension_office`, storing, endpoint, real-data smoke test).
