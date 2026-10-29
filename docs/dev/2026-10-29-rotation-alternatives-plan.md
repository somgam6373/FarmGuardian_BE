# Rotation Summary and Alternatives Implementation Plan (BE-43 / BE-44)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (project CLAUDE.md: no subagent-driven execution). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pure functions `rotation_summary` (BE-43) and `pick_alternatives` (BE-44) with the two types they need, tested by judgment rules §9 (RT1–RT3, A1–A5) and the additions in the design.

**Architecture:** `RotationItem` and `RotationSummary` in `app/judgment/domain/schemas.py`; both functions in `rules.py`. No new module, no DB, no clock.

**Tech Stack:** Python 3.13, Pydantic v2, pytest.

**Spec:** `docs/dev/2026-10-29-rotation-alternatives-design.md` (approved in chat 2026-10-29); rules in `docs/dev/팜가디언_판정_규칙.md` §6, §7, §9; frame = `docs/dev/팜가디언_API_명세.md` (never edited).

## Global Constraints

- `팜가디언_API_명세.md` is the frame and **must not change**: no commit of this plan touches it.
- `RotationSummary` serializes (`model_dump(mode="json")`) to the spec's `Rotation`: `{"window_start": ISO date | null, "total": int, "items": [{"moa": {"label_kr", "system", "code"} | null, "count": int}]}`.
- `rotation_summary`: window = records with `sprayed_on >= planted_at` (whole history when `planted_at` is None, then `window_start` None); one record counts 1 whatever the drug; grouped by `moa.label_kr` with all records without `moa` forming one `moa=None` item; order `count` descending, then `label_kr` ascending, the `None` item last; the item's `moa` is that of the newest record of the group (`sprayed_on` descending, then `id` descending).
- `pick_alternatives`: keep an item only if `verdict` is `OK`, `moa` is not None, and (when `selected.moa` is not None) `moa.label_kr != selected.moa.label_kr`; keep input order and the same objects.
- `app/judgment/domain/` imports no `sqlalchemy`, `fastapi`, `httpx` and never reads the clock (the existing guard test covers the new code).
- Code and identifiers in English, short Korean comments as in `app/core`; ruff line length 100 (Korean characters count double, wrap long strings); tests flat in `tests/`; commit messages in English; do not push.

## Review Focus

- The window edge: a record on `planted_at` counts, the day before does not; a history that is entirely before `planted_at` gives `total 0` and `items []`. (Task 1)
- Ordering: equal counts by `label_kr`, and the unknown (`None`) group last even when it has the most records. (Task 1)
- Records with the same `label_kr` but different `system`/`code` merge into one item that carries the newest record's `moa`. (Task 1)
- Alternatives never contain a non-`OK` result or one without `moa`, also when the selected drug has no `moa`; only the label decides "different group". (Task 2)
- Neither function changes its input, and `pick_alternatives` returns the very objects it was given. (Tasks 1, 2)

---

### Task 0: Commit the design and this plan

- [ ] **Step 1:** `git add docs/dev/2026-10-29-rotation-alternatives-design.md docs/dev/2026-10-29-rotation-alternatives-plan.md` / `git commit -m "Add rotation summary and alternatives design and plan"`

### Task 1: `rotation_summary`

**Files:**
- Modify: `app/judgment/domain/schemas.py`, `app/judgment/domain/rules.py`
- Test: `tests/test_judge_rotation_summary.py`

**Interfaces:**
- Produces in `schemas.py`: `RotationItem(moa: Moa | None, count: int)` and `RotationSummary(window_start: date | None, total: int, items: list[RotationItem])` (frozen like the other models).
- Produces in `rules.py`: `rotation_summary(history: Sequence[SprayRecord], planted_at: date | None) -> RotationSummary` per the constraints above.

- [ ] **Step 1: Write the failing tests** in `tests/test_judge_rotation_summary.py`
```python
from datetime import date

from app.judgment.domain.rules import rotation_summary
from app.judgment.domain.schemas import Moa, SprayRecord
from tests.judge_support import spray

PLANTED = date(2026, 5, 1)


def labels(summary):
    return [(i.moa.label_kr if i.moa else None, i.count) for i in summary.items]


def history(*specs):  # (계열, 월, 일): id는 1부터
    return [spray(n, label, date(2026, m, d)) for n, (label, m, d) in enumerate(specs, start=1)]


def test_rt1_counts_only_records_after_planting():
    records = history(
        ("가1", 6, 1), ("가1", 6, 2), ("가1", 6, 3), ("가1", 6, 4), ("가1", 4, 20),
        ("나2", 7, 1), ("나2", 7, 2), (None, 8, 1),
    )
    s = rotation_summary(records, PLANTED)

    assert (s.window_start, s.total) == (PLANTED, 7)
    assert labels(s) == [("가1", 4), ("나2", 2), (None, 1)]


def test_rt2_no_history():
    s = rotation_summary([], PLANTED)

    assert (s.total, s.items) == (0, [])


def test_rt3_no_planting_date_uses_the_whole_history():
    records = [
        spray(1, "가1", date(2025, 8, 1)),
        spray(2, "가1", date(2026, 6, 1)),
        spray(3, "나2", date(2026, 7, 1)),
    ]
    s = rotation_summary(records, None)

    assert (s.window_start, s.total) == (None, 3)
    assert labels(s) == [("가1", 2), ("나2", 1)]


def test_record_on_planting_day_counts_and_the_day_before_does_not():
    assert rotation_summary(history(("가1", 5, 1)), PLANTED).total == 1
    assert rotation_summary(history(("가1", 4, 30)), PLANTED).total == 0


def test_history_only_before_planting_gives_an_empty_summary():
    s = rotation_summary(history(("가1", 3, 1), ("나2", 4, 1)), PLANTED)

    assert (s.window_start, s.total, s.items) == (PLANTED, 0, [])


def test_ties_are_ordered_by_label():
    s = rotation_summary(history(("나2", 6, 1), ("가1", 6, 2)), PLANTED)

    assert labels(s) == [("가1", 1), ("나2", 1)]


def test_unknown_group_is_last_even_with_the_most_records():
    s = rotation_summary(history((None, 6, 1), (None, 6, 2), (None, 6, 3), ("가1", 6, 4)), PLANTED)

    assert labels(s) == [("가1", 1), (None, 3)]


def test_same_label_with_different_system_merges_using_the_newest_moa():
    old = SprayRecord(
        id=1, pesticide_id=10, item_name="품목A", sprayed_on=date(2026, 6, 1),
        moa=Moa(label_kr="가1"),
    )
    new = SprayRecord(
        id=2, pesticide_id=10, item_name="품목A", sprayed_on=date(2026, 6, 2),
        moa=Moa(label_kr="가1", system="FRAC", code="4"),
    )
    s = rotation_summary([old, new], PLANTED)

    assert len(s.items) == 1
    assert s.items[0].count == 2
    assert s.items[0].moa == Moa(label_kr="가1", system="FRAC", code="4")


def test_counts_records_not_drugs():
    records = [
        spray(1, "가1", date(2026, 6, 1), item_name="품목A"),
        spray(2, "가1", date(2026, 6, 2), item_name="품목B", pesticide_id=11),
    ]

    assert labels(rotation_summary(records, PLANTED)) == [("가1", 2)]


def test_serializes_to_the_spec_shape():
    s = rotation_summary(history(("가1", 6, 1), ("가1", 6, 2), (None, 6, 3)), PLANTED)

    assert s.model_dump(mode="json") == {
        "window_start": "2026-05-01",
        "total": 3,
        "items": [
            {"moa": {"label_kr": "가1", "system": None, "code": None}, "count": 2},
            {"moa": None, "count": 1},
        ],
    }


def test_input_history_is_not_changed():
    records = history(("가1", 6, 3), ("나2", 6, 1), ("가1", 6, 2))
    before = list(records)

    rotation_summary(records, PLANTED)

    assert records == before
```
- [ ] **Step 2: Run** `.venv\Scripts\python -m pytest tests\test_judge_rotation_summary.py -q` — Expected: collection ERROR `cannot import name 'rotation_summary'`.
- [ ] **Step 3: Implement** `RotationItem`, `RotationSummary` (schemas) and `rotation_summary` (rules) per the constraints; reuse `_newest_first` for the "newest record's `moa`" rule.
- [ ] **Step 4: Run** the step 2 command — Expected: `11 passed`. Full suite and `ruff check .` clean (wrap long lines).
- [ ] **Step 5: Commit** `git add app/judgment tests/test_judge_rotation_summary.py` / `git commit -m "Add rotation summary"`
- [ ] **Step 6: Mutation check.** In `rotation_summary` change `>= planted_at` to `> planted_at`, run `tests\test_judge_rotation_summary.py` — Expected: `test_record_on_planting_day_counts_and_the_day_before_does_not` FAILS; restore with `git checkout -- app/judgment/domain/rules.py`; re-run — `11 passed`; `git status --short` clean.

### Task 2: `pick_alternatives`

**Files:**
- Modify: `app/judgment/domain/rules.py`
- Test: `tests/test_judge_alternatives.py`

**Interfaces:**
- Consumes: `JudgeResult`, `Verdict`, `Moa` (existing).
- Produces: `pick_alternatives(selected: JudgeResult, others: Sequence[JudgeResult]) -> list[JudgeResult]` per the constraints above.

- [ ] **Step 1: Write the failing tests** in `tests/test_judge_alternatives.py`
```python
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
```
- [ ] **Step 2: Run** `.venv\Scripts\python -m pytest tests\test_judge_alternatives.py -q` — Expected: collection ERROR `cannot import name 'pick_alternatives'`.
- [ ] **Step 3: Implement `pick_alternatives`** in `rules.py` per the constraints.
- [ ] **Step 4: Run** the step 2 command — Expected: `10 passed` (A1, A2, three A3, A4, A5, other system, order/identity, empty). Full suite and `ruff check .` clean.
- [ ] **Step 5: Commit** `git add app/judgment/domain/rules.py tests/test_judge_alternatives.py` / `git commit -m "Add alternatives pick"`
- [ ] **Step 6: Mutation check.** In `pick_alternatives` drop the `moa is not None` condition, run `tests\test_judge_alternatives.py` — Expected: `test_a4_ok_without_moa_is_dropped` and `test_a5_selected_without_moa_skips_only_the_group_comparison` FAIL; restore with `git checkout -- app/judgment/domain/rules.py`; re-run — `10 passed`; `git status --short` clean.

### Task 3: Final verification

- [ ] **Step 1:** `.venv\Scripts\python -m pytest -q -rs` and `.venv\Scripts\ruff check .` — Expected: all pass, `All checks passed!`.
- [ ] **Step 2:** `git diff --name-only origin/test..HEAD` lists no `팜가디언_API_명세.md`; `git status -sb` clean; `git log --oneline origin/test..HEAD` shows 3 commits. Do not push.
- [ ] **Step 3:** Tell the user: the judgment domain is complete (`rotation_summary`, `pick_alternatives`); BE-45 remains (conversion from static rows, service: candidate pool, sorting, names, `show_extension_office`, notices, storing, endpoints, real-data smoke test).
