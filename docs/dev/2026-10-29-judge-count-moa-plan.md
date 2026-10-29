# Judgment ③ Count and ④ Action Group Implementation Plan (BE-40 / BE-41)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (project CLAUDE.md: no subagent-driven execution). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pure functions `check_count` (③), `check_moa` (④) and `rotation_rule` (④ rule table), tested by the ③④ rows of judgment rules §9, producing results in exactly the shape of the API spec.

**Architecture:** Extend `app/judgment/domain/rules.py` and `schemas.py` (adds `RotationRule`). The conditions, messages, `facts` and `evidence` are the tables in the design document; this plan fixes the tasks, signatures and tests.

**Tech Stack:** Python 3.13, Pydantic v2, pytest. `tests/` may import `app.catalog.infrastructure.static_data`.

**Spec:** `docs/dev/2026-10-29-judge-count-moa-design.md` (approved in chat 2026-10-29); rules in `docs/dev/팜가디언_판정_규칙.md` §3, §4 ③④, §8, §9; frame = `docs/dev/팜가디언_API_명세.md` (never edited).

## Global Constraints

- `팜가디언_API_명세.md` is the frame and **must not change**: no commit of this plan touches it.
- `facts` of ③ always have the 8 keys `used, max_uses, remaining, remaining_after, since, item_name, strict_use_method, no_limit`; `facts` of ④ always have the 6 keys `label, rule, max_consecutive, consecutive, unknown, window`; `null` where a value does not exist. Dates in `facts` are ISO strings.
- Messages are copied from the design tables (= judgment rules §8) character for character; none contains `추천 예측 예상 가능성 위험 확률 안전 문제없`.
- The ④ rule table follows judgment rules §4 ④ as decided: 생1, 생2, `미분류(살균제)`, plain `미분류` and groups without `system` are 「그 밖의 계열」 (1 in a row). `NO_LIMIT` = `카`, `8a`–`8f`, `13`, `미분류(살충제)`.
- Rule `source` strings are exactly those of `rotation_rule.json`.
- `app/judgment/domain/` imports no `sqlalchemy`, `fastapi`, `httpx` and never reads the clock.
- Code and identifiers in English, short Korean comments as in `app/core`; ruff line length 100 (Korean characters count double, wrap long strings); tests flat in `tests/`; commit messages in English; do not push.

## Review Focus

- ③ order: an unreadable `max_uses` shows before 「정식일 없음」, and all-`NO_LIMIT` ignores `planted_at` and `history_confirmed`; a `CHECK` row with numbers is still unreadable. (Task 3, C11/C16/C18)
- ③ counting: same-day sprays count separately, a spray on `planted_at` counts, one day before does not, other items never count, over-use gives `remaining` 0 and `remaining_after` None. (Task 3, C12/C17, boundary)
- ④ order: the newest records decide; a record without `moa` or with another group stops the run; same-day records are ordered by `id`; `unknown` counts only the newest three. (Task 2, M5/M7/M8 and additions)
- Compound labels: strictest part wins, `NO_LIMIT` only if all parts are, a part without known `system` is 「그 밖의 계열」. (Task 1)
- Every row of `moa.json` gets a rule, the `NO_LIMIT` set is exactly the four labels, 생1/생2 are not `NO_LIMIT`, and the hard-coded table equals `rotation_rule.json`. (Task 1)

---

### Task 0: Commit the design and this plan

- [ ] **Step 1:** `git add docs/dev/2026-10-29-judge-count-moa-design.md docs/dev/2026-10-29-judge-count-moa-plan.md` / `git commit -m "Add judgment count and action group design and plan"`

### Task 1: Rule table and test builders

**Files:**
- Modify: `app/judgment/domain/schemas.py`, `app/judgment/domain/rules.py`, `tests/judge_support.py`
- Test: `tests/test_judge_rotation_rule.py`

**Interfaces:**
- Produces in `schemas.py`: `RotationRule(kind: Literal["NO_LIMIT", "CONSECUTIVE"], max_consecutive: int | None, source: str)` (frozen like the other models).
- Produces in `rules.py`: `rotation_rule(moa: Moa) -> RotationRule` and `moa_label(moa: Moa) -> str` (`label_kr`, plus ` ({system} {code})` when both are set).
- Produces in `tests/judge_support.py`: `spray(sid: int, label: str | None, on: date, item_name: str = "품목A", pesticide_id: int = 10) -> SprayRecord` (`label` None → `moa` None, else `Moa(label_kr=label)`) and `recent(*labels: str | None) -> list[SprayRecord]` (labels newest first; the newest is 2026-09-01, each older one a day earlier, the newest has the highest `id`; the list is returned **oldest first** so the checks must sort).

`rotation_rule` (design, rule table): a label without `+` is looked up with its `system`; a compound label is split on `+` and each part is looked up with no `system`. A part is, first match wins: `카` → NO_LIMIT, source 「FRAC Multi-site Guidelines」; `8a`…`8f`, `13`, `미분류(살충제)` → NO_LIMIT, 「IRAC 예외 그룹」; `가1` → 2, 「FRAC Phenylamides (last updated March 2020)」; `아5` → 2, 「FRAC CAA WG 2026 회의록 3.2절」; `system == "IRAC"` → 2, 「IRAC MoA Classification v11.5 (Feb 2026)」; anything else → 1, 「농식품부 PLS 안내」. Compound: NO_LIMIT only if every part is (source of the first part); otherwise the smallest `max_consecutive`, source of the first part with that value.

- [ ] **Step 1: Write the failing tests** in `tests/test_judge_rotation_rule.py`
```python
import pytest

from app.catalog.infrastructure.static_data import load
from app.judgment.domain.rules import moa_label, rotation_rule
from app.judgment.domain.schemas import Moa

MULTI = "FRAC Multi-site Guidelines"
EXCEPTION = "IRAC 예외 그룹"
PHENYL = "FRAC Phenylamides (last updated March 2020)"
CAA = "FRAC CAA WG 2026 회의록 3.2절"
IRAC = "IRAC MoA Classification v11.5 (Feb 2026)"
PLS = "농식품부 PLS 안내"
N, C = "NO_LIMIT", "CONSECUTIVE"

TABLE = [
    ("카", "FRAC", N, None, MULTI),
    *[(f"8{c}", "IRAC", N, None, EXCEPTION) for c in "abcdef"],
    ("13", "IRAC", N, None, EXCEPTION),
    ("미분류(살충제)", None, N, None, EXCEPTION),
    ("가1", "FRAC", C, 2, PHENYL),
    ("아5", "FRAC", C, 2, CAA),
    ("28", "IRAC", C, 2, IRAC),
    ("다3", "FRAC", C, 1, PLS),
    ("생1", "FRAC", C, 1, PLS),
    ("생2", "FRAC", C, 1, PLS),
    ("미분류(살균제)", None, C, 1, PLS),
    ("미분류", None, C, 1, PLS),
    ("가5", None, C, 1, PLS),
]


@pytest.mark.parametrize("label,system,kind,max_consecutive,source", TABLE)
def test_rule_table(label, system, kind, max_consecutive, source):
    rule = rotation_rule(Moa(label_kr=label, system=system))

    assert (rule.kind, rule.max_consecutive, rule.source) == (kind, max_consecutive, source)


@pytest.mark.parametrize(
    "label,kind,max_consecutive,source",
    [
        ("카+가1", C, 2, PHENYL),
        ("카+라3", C, 1, PLS),
        ("카+13", N, None, MULTI),
        ("13+22b", C, 1, PLS),
        ("카+아5+다3", C, 1, PLS),
        ("가1+아5", C, 2, PHENYL),
    ],
)
def test_compound_label_uses_the_strictest_part(label, kind, max_consecutive, source):
    rule = rotation_rule(Moa(label_kr=label))

    assert (rule.kind, rule.max_consecutive, rule.source) == (kind, max_consecutive, source)


def test_rule_table_equals_rotation_rule_json():  # RULE1
    sample = {  # rule_id → 그 규칙에 해당하는 계열
        1: Moa(label_kr="28", system="IRAC", code="28"),
        2: Moa(label_kr="다3", system="FRAC", code="3"),
        3: Moa(label_kr="가1", system="FRAC", code="4"),
        4: Moa(label_kr="아5", system="FRAC", code="40"),
        5: Moa(label_kr="카", system="FRAC", code="M"),
        6: Moa(label_kr="13", system="IRAC", code="13"),
    }
    rows = load("rotation_rule")

    assert {r["rule_id"] for r in rows} == set(sample)
    for r in rows:
        rule = rotation_rule(sample[r["rule_id"]])
        assert rule.source == r["source"]
        assert rule.max_consecutive == r["max_consecutive"]
        assert (rule.kind == N) == (r["max_consecutive"] is None)


def test_every_moa_row_gets_a_rule_and_only_four_labels_are_unlimited():
    unlimited = set()
    for m in load("moa"):
        system, _, code = (m["intl_code"] or "").partition(" ")
        moa = Moa(label_kr=m["kr_code"], system=system or None, code=code or None)
        if rotation_rule(moa).kind == N:
            unlimited.add(m["kr_code"])

    assert unlimited == {"카", "8f", "13", "미분류(살충제)"}


def test_moa_label():
    assert moa_label(Moa(label_kr="가1", system="FRAC", code="4")) == "가1 (FRAC 4)"
    assert moa_label(Moa(label_kr="카+가1")) == "카+가1"
    assert moa_label(Moa(label_kr="가1", system="FRAC")) == "가1"
```
- [ ] **Step 2: Run** `.venv\Scripts\python -m pytest tests\test_judge_rotation_rule.py -q` — Expected: collection ERROR `cannot import name 'moa_label'`.
- [ ] **Step 3: Implement** `RotationRule` (schemas), `rotation_rule` and `moa_label` (rules) per the interface block; add `spray` and `recent` to `tests/judge_support.py`.
- [ ] **Step 4: Run** the step 2 command — Expected: `27 passed` (18 table cases, 6 compound cases, 3 single tests). Full suite and `ruff check .` clean.
- [ ] **Step 5: Commit** `git add app/judgment tests/judge_support.py tests/test_judge_rotation_rule.py` / `git commit -m "Add rotation rule table"`

### Task 2: ④ action group

**Files:**
- Modify: `app/judgment/domain/rules.py`
- Test: `tests/test_judge_moa.py`

**Interfaces:**
- Consumes: `rotation_rule`, `moa_label` (Task 1), `rows_data_asof` (existing), `spray`/`recent`/`make_input`/`reg`.
- Produces: `check_moa(inp: JudgeInput) -> CheckResult` (`key="moa"`, `evidence.data_asof = rows_data_asof(inp)`), conditions and messages from the design table ④ #1–#7, ordering and `facts` rules from the bullets below it. Add a private helper that returns the history newest first (`sprayed_on` descending, then `id` descending).

- [ ] **Step 1: Write the failing tests** in `tests/test_judge_moa.py`
```python
from datetime import date

import pytest

from app.judgment.domain.rules import check_moa
from app.judgment.domain.schemas import Moa, Verdict
from tests.judge_support import make_input, recent, reg, spray

PHENYL = "FRAC Phenylamides (last updated March 2020)"
OK, CAUTION, NEEDS_CHECK = Verdict.OK, Verdict.CAUTION, Verdict.NEEDS_CHECK
LABEL = "가1 (FRAC 4)"
UNCONFIRMED = "살포 기록에 빠진 것이 없는지 확인되지 않았습니다. 기록을 입력하고 「누락 없음」을 선택해 주세요"


def run(**kw):
    return check_moa(make_input(**kw))


def mfacts(label=LABEL, rule="CONSECUTIVE", mx=2, consecutive=0, unknown=0, window=()):
    return {
        "label": label,
        "rule": rule,
        "max_consecutive": mx,
        "consecutive": consecutive,
        "unknown": unknown,
        "window": list(window),
    }


def win(rec_id, iso, label):
    return {"id": rec_id, "sprayed_on": iso, "item_name": "품목A", "label": label}


def test_m1_no_history():
    r = run(history=[])

    assert (r.key, r.status, r.message) == ("moa", OK, "살포 이력이 없습니다")
    assert r.facts == mfacts()
    assert r.evidence.source_text == PHENYL
    assert r.evidence.data_asof == date(2026, 10, 1)


def test_m2_unconfirmed_without_history():
    r = run(history=[], history_confirmed=False)

    assert (r.status, r.message) == (NEEDS_CHECK, UNCONFIRMED)


def test_m3_one_in_a_row_is_ok():
    r = run(history=recent("가1", "나2", "가1"))

    assert r.status is OK
    assert r.message == f"{LABEL} — 직전까지 같은 계열을 연속 1회 사용했습니다 (연속 2회까지 기준)"
    assert r.facts["consecutive"] == 1
    assert r.evidence.source_text == PHENYL


def test_m4_reaching_the_limit_is_caution_with_a_three_record_window():
    r = run(history=recent("가1", "가1", "나2"))

    assert r.status is CAUTION
    assert r.message == (
        f"{LABEL} — 직전까지 같은 계열을 연속 2회 사용했습니다. "
        "연속 2회까지가 기준이라 같은 작용기작이 반복됩니다"
    )
    assert r.facts == mfacts(
        consecutive=2,
        window=[
            win(3, "2026-09-01", "가1"),
            win(2, "2026-08-31", "가1"),
            win(1, "2026-08-30", "나2"),
        ],
    )


def test_m5_newest_record_of_another_group_breaks_the_run():
    r = run(history=recent("나2", "가1", "가1"))

    assert (r.status, r.message) == (OK, f"{LABEL} — 직전 살포는 다른 계열입니다")
    assert r.facts["consecutive"] == 0


def test_m6_chosen_drug_without_moa():
    r = run(moa=None, history=recent("가1", "가1"))

    assert (r.status, r.message) == (
        NEEDS_CHECK,
        "이 약제의 작용기작 정보가 없어 비교할 수 없습니다",
    )
    assert r.evidence.source_text == "없음"
    assert r.facts == {
        "label": None,
        "rule": None,
        "max_consecutive": None,
        "consecutive": None,
        "unknown": None,
        "window": [],
    }


def test_m7_unknown_record_breaks_the_run_and_is_counted():
    r = run(history=recent(None, "가1", "가1"))

    assert r.status is OK
    assert r.message == f"{LABEL} — 직전 살포는 다른 계열입니다 (작용기작 미상 1건 포함)"
    assert (r.facts["consecutive"], r.facts["unknown"]) == (0, 1)
    assert r.facts["window"][0]["label"] is None


def test_m8_same_day_records_are_ordered_by_id():
    history = [
        spray(3, "가1", date(2026, 8, 30)),
        spray(4, "가1", date(2026, 9, 1)),
        spray(5, "나2", date(2026, 9, 1)),
    ]
    r = run(history=history)

    assert [w["id"] for w in r.facts["window"]] == [5, 4, 3]
    assert (r.status, r.facts["consecutive"]) == (OK, 0)


def test_m9_unconfirmed_history_is_needs_check_not_caution():
    r = run(history=recent("가1", "가1"), history_confirmed=False)

    assert (r.status, r.message) == (NEEDS_CHECK, UNCONFIRMED)
    assert r.facts["consecutive"] == 2  # 이력에서 계산한 값은 보여 준다


@pytest.mark.parametrize(
    "chosen,labels,status,rule,mx,consecutive,message",
    [
        (Moa(label_kr="카", system="FRAC", code="M"), ["카", "카", "카"], OK, "NO_LIMIT", None, 3,
         "카 (FRAC M) — 같은 계열을 반복해도 제한이 없는 계열입니다"),
        (Moa(label_kr="8f", system="IRAC", code="8F"), ["8f", "8f", "8f"], OK, "NO_LIMIT", None, 3,
         "8f (IRAC 8F) — 같은 계열을 반복해도 제한이 없는 계열입니다"),
        (Moa(label_kr="28", system="IRAC", code="28"), ["28", "28", "나2"], CAUTION,
         "CONSECUTIVE", 2, 2, None),
        (Moa(label_kr="28", system="IRAC", code="28"), ["28", "나2"], OK, "CONSECUTIVE", 2, 1, None),
        (Moa(label_kr="다3", system="FRAC", code="3"), ["다3"], CAUTION, "CONSECUTIVE", 1, 1, None),
        (Moa(label_kr="카+가1"), ["카+가1", "카+가1"], CAUTION, "CONSECUTIVE", 2, 2, None),
        (Moa(label_kr="카+라3"), ["카+라3"], CAUTION, "CONSECUTIVE", 1, 1, None),
        (Moa(label_kr="가1", system="FRAC", code="4"), ["가1", "가1", "가1"], CAUTION,
         "CONSECUTIVE", 2, 3, None),
    ],
    ids=["M10", "M11", "M12", "M13", "M14", "M15", "M16", "M17"],
)
def test_m10_to_m17_rules_by_group(chosen, labels, status, rule, mx, consecutive, message):
    r = run(moa=chosen, history=recent(*labels))

    assert r.status is status
    assert (r.facts["rule"], r.facts["max_consecutive"], r.facts["consecutive"]) == (
        rule, mx, consecutive,
    )
    if message:
        assert r.message == message


def test_no_limit_wins_over_an_empty_history():
    r = run(moa=Moa(label_kr="카", system="FRAC", code="M"), history=[])

    assert r.message == "카 (FRAC M) — 같은 계열을 반복해도 제한이 없는 계열입니다"


def test_window_has_at_most_three_records_and_unknown_counts_only_those():
    r = run(history=recent("가1", "가1", "가1", None))

    assert len(r.facts["window"]) == 3
    assert (r.facts["consecutive"], r.facts["unknown"]) == (3, 0)


def test_only_the_newest_run_counts():
    r = run(history=recent("가1", "나2", "나2"))

    assert r.facts["consecutive"] == 1


def test_unknown_note_is_added_to_the_caution_message_too():
    r = run(history=recent("가1", "가1", None))

    assert r.status is CAUTION
    assert r.message.endswith("같은 작용기작이 반복됩니다 (작용기작 미상 1건 포함)")


def test_works_without_planting_date_and_ignores_registration():  # C6의 ④ 부분
    r = run(planted_at=None, registrations=[], history=recent("가1"))

    assert r.status is OK
    assert r.message == f"{LABEL} — 직전까지 같은 계열을 연속 1회 사용했습니다 (연속 2회까지 기준)"
```
- [ ] **Step 2: Run** `.venv\Scripts\python -m pytest tests\test_judge_moa.py -q` — Expected: collection ERROR `cannot import name 'check_moa'`.
- [ ] **Step 3: Implement `check_moa`** per the design table ④ and its bullets (recent-first order, `consecutive`, `window` of 3 as `{id, sprayed_on (ISO), item_name, label}`, `unknown` inside the window, the unknown note on #3/#5/#6/#7 messages, facts for `moa` None).
- [ ] **Step 4: Run** the step 2 command — Expected: `22 passed` (9 M-cases, 8 parametrized M10–M17, 5 additions). Full suite and `ruff check .` clean.
- [ ] **Step 5: Commit** `git add app/judgment/domain/rules.py tests/test_judge_moa.py` / `git commit -m "Add action group check"`

### Task 3: ③ count

**Files:**
- Modify: `app/judgment/domain/rules.py`
- Test: `tests/test_judge_count.py`

**Interfaces:**
- Consumes: `considered_rows`, `calc_rows`, `rows_data_asof`, `format_date_kr` (existing), `check_registration`.
- Produces: `check_count(inp: JudgeInput, registration: CheckResult) -> CheckResult` (`key="count"`), conditions #1–#7, `max`/strict row/`used`/`since`/suffix rules and `facts` rules from the design section ③. The unreadable row is the first `calc` row whose `max_uses` is None or whose `usage_type` is `CHECK`.

- [ ] **Step 1: Write the failing tests** in `tests/test_judge_count.py`
```python
from datetime import date

import pytest

from app.judgment.domain.rules import check_count, check_registration
from app.judgment.domain.schemas import Verdict
from tests.judge_support import make_input, reg, spray

OK, BLOCKED, NEEDS_CHECK = Verdict.OK, Verdict.BLOCKED, Verdict.NEEDS_CHECK
METHOD = "발생 초부터 경엽처리"
UNCONFIRMED = "살포 기록에 빠진 것이 없는지 확인되지 않았습니다. 기록을 입력하고 「누락 없음」을 선택해 주세요"
NO_PLANTING = "정식일이 없어 이번 작기 사용 횟수를 셀 수 없습니다. 정식일을 입력해 주세요"


def count(**kw):
    inp = make_input(**kw)
    return check_count(inp, check_registration(inp))


def cfacts(used=None, mx=None, remaining=None, after=None, since="2026-05-01",
           method=None, no_limit=False):
    return {
        "used": used,
        "max_uses": mx,
        "remaining": remaining,
        "remaining_after": after,
        "since": since,
        "item_name": "품목A",
        "strict_use_method": method,
        "no_limit": no_limit,
    }


def a(sid, month, day, **kw):  # 품목A(가1) 살포
    return spray(sid, "가1", date(2026, month, day), **kw)


def unreadable(raw):
    return f"최대 사용 횟수 기준을 읽지 못했습니다. 원문: {raw}"


OTHER_ITEM = [spray(1, "나2", date(2026, 6, 1), item_name="품목B")]

COUNTED = [
    ("C1", OTHER_ITEM, 0, OK, "남은 횟수 3회, 이번 사용 후 2회입니다 (최대 3회)"),
    ("C2", [a(1, 6, 1)], 1, OK, "남은 횟수 2회, 이번 사용 후 1회입니다 (최대 3회)"),
    ("C3", [a(1, 6, 1), a(2, 6, 15)], 2, OK,
     "남은 횟수 1회, 이번 사용 후 0회입니다 (최대 3회). 이번이 마지막 사용입니다"),
    ("C4", [a(1, 6, 1), a(2, 6, 15), a(3, 7, 1)], 3, BLOCKED,
     "5월 1일부터 3회 사용해 최대 3회를 채웠습니다. 남은 횟수는 0회입니다"),
    ("C5", [a(1, 4, 20), a(2, 6, 1)], 1, OK, "남은 횟수 2회, 이번 사용 후 1회입니다 (최대 3회)"),
    ("C7", [a(1, 6, 1, pesticide_id=10), a(2, 6, 10, pesticide_id=11)], 2, OK,
     "남은 횟수 1회, 이번 사용 후 0회입니다 (최대 3회). 이번이 마지막 사용입니다"),
    ("C10", [], 0, OK, "남은 횟수 3회, 이번 사용 후 2회입니다 (최대 3회)"),
    ("C12", [a(1, 6, 1), a(2, 6, 1)], 2, OK,
     "남은 횟수 1회, 이번 사용 후 0회입니다 (최대 3회). 이번이 마지막 사용입니다"),
    ("C14", [a(1, 4, 1)], 0, OK, "남은 횟수 3회, 이번 사용 후 2회입니다 (최대 3회)"),
    ("C17", [a(1, 6, 1), a(2, 6, 15), a(3, 7, 1), a(4, 8, 1)], 4, BLOCKED,
     "5월 1일부터 4회 사용해 최대 3회를 채웠습니다. 남은 횟수는 0회입니다"),
    ("on-planting-day", [a(1, 5, 1)], 1, OK, "남은 횟수 2회, 이번 사용 후 1회입니다 (최대 3회)"),
    ("day-before", [a(1, 4, 30)], 0, OK, "남은 횟수 3회, 이번 사용 후 2회입니다 (최대 3회)"),
]


@pytest.mark.parametrize(
    "history,used,status,message", [c[1:] for c in COUNTED], ids=[c[0] for c in COUNTED]
)
def test_counting_and_messages(history, used, status, message):
    r = count(history=history)

    assert (r.key, r.status, r.message) == ("count", status, message)
    remaining = max(3 - used, 0)
    after = None if status is BLOCKED else remaining - 1
    assert r.facts == cfacts(used, 3, remaining, after, method=METHOD)


def test_ok_evidence_is_the_strict_rows_raw_text():
    r = count()

    assert r.evidence.source_text == "3회 이내"
    assert r.evidence.data_asof == date(2026, 10, 1)


def test_c6_no_planting_date():
    r = count(planted_at=None, history=[a(1, 6, 1)])

    assert (r.status, r.message) == (NEEDS_CHECK, NO_PLANTING)
    assert r.facts == cfacts(since=None)


def test_c9_and_c15_unconfirmed_history():
    for history in ([], [a(1, 6, 1)]):
        r = count(history=history, history_confirmed=False)

        assert (r.status, r.message) == (NEEDS_CHECK, UNCONFIRMED)
        assert r.facts == cfacts()


def test_c16_planting_date_is_asked_before_the_confirmation():
    r = count(planted_at=None, history_confirmed=False)

    assert r.message == NO_PLANTING


def test_c11_unreadable_max_shows_the_raw_text_and_beats_the_planting_date():
    r = count(registrations=[reg(max_uses=None, use_num_raw="-")], planted_at=None)

    assert (r.status, r.message) == (NEEDS_CHECK, unreadable("-"))
    assert r.evidence.source_text == "-"
    assert r.facts == cfacts(since=None)


def test_check_row_with_numbers_is_still_unreadable():
    r = count(registrations=[reg(usage_type="CHECK", max_uses=3, use_num_raw="연1회")])

    assert (r.status, r.message) == (NEEDS_CHECK, unreadable("연1회"))


def test_unreadable_raw_text_is_the_first_unreadable_rows_and_none_when_empty():
    rows = [reg(max_uses=None, use_num_raw="A"), reg(max_uses=None, use_num_raw="B")]
    assert count(registrations=rows).evidence.source_text == "A"

    r = count(registrations=[reg(max_uses=None, use_num_raw=None)])
    assert r.message == unreadable("없음")
    assert r.evidence.source_text == "없음"


def test_c13_no_pest_takes_the_smallest_max_of_all_rows():
    rows = [reg(max_uses=5), reg(pest_id=2, pest_name="역병", max_uses=3)]
    r = count(pest_id=None, registrations=rows)

    assert r.facts["max_uses"] == 3


def test_c18_all_no_limit_ignores_planting_date_and_confirmation():
    row = reg(usage_type="NO_LIMIT", phi_days=None, max_uses=None, use_num_raw="-")
    r = count(registrations=[row], planted_at=None, history_confirmed=False)

    assert (r.status, r.message) == (
        OK,
        "사용 횟수 제한이 없는 약제입니다. 라벨의 사용 방법을 확인해 주세요",
    )
    assert r.facts == cfacts(since=None, no_limit=True)
    assert r.evidence.source_text == "-"


def test_c19_all_at_planting_still_counts():
    row = reg(usage_type="AT_PLANTING", phi_days=None, max_uses=1, use_num_raw="1회")
    r = count(registrations=[row], history=[])

    assert (r.status, r.facts["used"], r.facts["max_uses"]) == (OK, 0, 1)
    assert r.message == "남은 횟수 1회, 이번 사용 후 0회입니다 (최대 1회). 이번이 마지막 사용입니다"


def test_c20_strictest_use_method_is_named():
    rows = [
        reg(max_uses=3, use_method="경엽처리"),
        reg(max_uses=1, use_num_raw="1회", use_method="무인항공"),
    ]
    r = count(registrations=rows)

    assert r.facts["strict_use_method"] == "무인항공"
    assert r.message == (
        "남은 횟수 1회, 이번 사용 후 0회입니다 (최대 1회). 이번이 마지막 사용입니다 (무인항공 기준)"
    )
    assert r.evidence.source_text == "1회"


def test_c21_no_limit_row_is_left_out():
    rows = [reg(max_uses=3), reg(usage_type="NO_LIMIT", phi_days=None, max_uses=None)]
    r = count(registrations=rows)

    assert (r.status, r.facts["max_uses"], r.facts["no_limit"]) == (OK, 3, False)


def test_blocked_registration_makes_count_needs_check():
    r = count(registrations=[])

    assert (r.status, r.message) == (NEEDS_CHECK, "등록 정보가 없어 확인할 수 없습니다")
    assert r.evidence.source_text == "없음"
    assert r.facts == cfacts()


def test_blocked_message_names_the_year_when_it_differs():
    history = [a(1, 6, 1), a(2, 6, 15), a(3, 7, 1)]
    r = count(planted_at=date(2025, 11, 1), history=history + [spray(4, "가1", date(2025, 12, 1))])

    assert r.status is BLOCKED
    assert r.message.startswith("2025년 11월 1일부터 4회 사용해")
```
- [ ] **Step 2: Run** `.venv\Scripts\python -m pytest tests\test_judge_count.py -q` — Expected: collection ERROR `cannot import name 'check_count'`.
- [ ] **Step 3: Implement `check_count`** per the design table ③ (conditions in that order, the `max`/strict row/`used`/`since` rules, the use-method suffix on OK and BLOCKED messages, the `facts` rules).
- [ ] **Step 4: Run** the step 2 command — Expected: `26 passed` (12 parametrized counting cases, 14 single tests). Full suite and `ruff check .` clean.
- [ ] **Step 5: Commit** `git add app/judgment/domain/rules.py tests/test_judge_count.py` / `git commit -m "Add count check"`
- [ ] **Step 6: Mutation check.** In `check_count` swap the `>=` of `used >= max` for `>`, run `tests\test_judge_count.py` — Expected: the C4 and C17 cases FAIL; restore with `git checkout -- app/judgment/domain/rules.py`; re-run — all pass; `git status --short` clean.

### Task 4: Message scan for all four checks and final verification

**Files:**
- Modify: `tests/test_judge_domain_rules.py`

- [ ] **Step 1: Extend the scan test** (it is characterization of messages already tested elsewhere; it passes on the first run). In `tests/test_judge_domain_rules.py` import `check_count`, `check_moa`, `recent`, `spray` and `Moa`; append to `SCAN_INPUTS`: `{"history": recent("가1", "가1")}`, `{"history": recent("가1", "나2")}`, `{"history": recent(None, "가1")}`, `{"history": [spray(i, "가1", date(2026, 6, i)) for i in (1, 2, 3)]}`, `{"history": [spray(i, "가1", date(2026, 6, i)) for i in (1, 2)]}`, `{"moa": None}`, `{"history_confirmed": False}`, `{"planted_at": None}`, `{"registrations": [reg(max_uses=None)]}`, `{"registrations": [reg(usage_type="NO_LIMIT", phi_days=None, max_uses=None)]}`, `{"moa": Moa(label_kr="카", system="FRAC", code="M")}`. Rename the test to `test_no_forbidden_word_in_any_check_message` and scan all four results (`registration`, `check_timing`, `check_count`, `check_moa`).
- [ ] **Step 2: Run** `.venv\Scripts\python -m pytest tests\test_judge_domain_rules.py -q` — Expected: all pass.
- [ ] **Step 3: Commit** `git add tests/test_judge_domain_rules.py` / `git commit -m "Scan count and action group messages"`
- [ ] **Step 4: Final verification.** `.venv\Scripts\python -m pytest -q -rs` and `.venv\Scripts\ruff check .` — Expected: all pass, `All checks passed!`; `git diff --name-only origin/test..HEAD` lists no `팜가디언_API_명세.md`; `git status -sb` clean; `git log --oneline origin/test..HEAD` shows 5 commits. Do not push.
- [ ] **Step 5:** Tell the user: BE-40/41 done at domain level; open for BE-42 (`judge()`, `verdict`, `notices`, `JudgeResult.data_asof`), BE-43 (`rotation_summary`), BE-45 (row/`Moa` conversion from static data, service, API).
