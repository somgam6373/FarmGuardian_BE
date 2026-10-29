# Judgment ① Registration and ② Timing Implementation Plan (BE-38 / BE-39)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (project CLAUDE.md: no subagent-driven execution). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pure functions `check_registration` (①) and `check_timing` (②) with the types they need, tested by the ① and ② rows of judgment rules §9, producing results in exactly the shape of the API spec.

**Architecture:** `app/judgment/domain/schemas.py` (Pydantic v2 frozen models, judgment rules §2) and `rules.py` (pure functions, no DB/HTTP/clock). Tests are flat files; a shared builder `tests/judge_support.py` makes the §9 `base` fixture.

**Tech Stack:** Python 3.13, Pydantic v2 (already installed with FastAPI), pytest.

**Spec:** `docs/dev/2026-10-29-judge-registration-timing-design.md`; rules in `docs/dev/팜가디언_판정_규칙.md` §2–4, §8, §9; frame = `docs/dev/팜가디언_API_명세.md` (never edited).

## Global Constraints

- `팜가디언_API_명세.md` is the frame and **must not change**: no edit to that file in any commit of this plan.
- A check result serializes to the spec shape `{key, status, message, facts, evidence: {source_text, data_asof}}`; `status` values are exactly `OK`, `CAUTION`, `BLOCKED`, `NEEDS_CHECK`.
- `facts` keys: ① only the keys of the case (judgment rules §4 ①); ② always all five `phi_days, harvest_from, rows, strict_use_method, no_limit`. Dates in `facts` are ISO strings; `Evidence.data_asof` is a `date`.
- Messages are copied from judgment rules §8 character for character (honorific, no forbidden words `추천 예측 예상 가능성 위험 확률 안전 문제없`).
- Date text in messages: same year as `today` → `10월 11일`; otherwise `2027년 1월 8일` (no zero padding).
- `app/judgment/domain/` imports no `sqlalchemy`, `fastapi` or `httpx`, and never reads the clock (`today` is input).
- `CHECK` rows count as NULL whatever numbers they carry; `facts.rows` = number of considered rows (before `calc_rows`).
- Code and identifiers in English, short Korean comments as in `app/core`; ruff line length 100, rules E/F/I; tests flat in `tests/`; commit messages in English; do not push.

## Review Focus

- Registered pests are distinct and sorted by name, and `{n}` counts distinct pests (two rows of one pest count once). (Task 2, R6)
- ① OK evidence is 「없음」 when both `use_method` and `dilut_raw` are empty, and shows only the one that exists otherwise. (Task 2, R7)
- `evidence.data_asof` is the oldest `data_asof` of the considered rows, not of other pests' rows. (Task 2)
- A `CHECK` row that carries `phi_days` is still NULL for ② (real data: `use_id` 3539). (Task 3, T15)
- Row-type mixes: `AT_PLANTING` is dropped before `NO_LIMIT`, only while rows remain; all-`AT_PLANTING` and all-`NO_LIMIT` stay. (Task 3, T9–T11, T14 and the `calc_rows` table)
- Ties and unreadable raw text: equal `phi_days` pick the first row as strict; the raw text shown is the first unreadable row's, 「없음」 when empty. (Task 3, T16–T18)

---

### Task 0: Commit the design and this plan

- [ ] **Step 1:** `git add docs/dev/2026-10-29-judge-registration-timing-design.md docs/dev/2026-10-29-judge-registration-timing-plan.md` / `git commit -m "Add judgment registration and timing design and plan"`

### Task 1: Types and test builder

**Files:**
- Create: `app/judgment/__init__.py`, `app/judgment/domain/__init__.py` (both empty), `app/judgment/domain/schemas.py`, `tests/judge_support.py`
- Test: `tests/test_judge_schemas.py`

**Interfaces:**
- Produces in `schemas.py` (field names and types exactly as judgment rules §2; every model `frozen=True`): `Verdict(StrEnum)` with `OK, CAUTION, BLOCKED, NEEDS_CHECK`; `Moa(label_kr: str, system: str | None = None, code: str | None = None)`; `Registration(pest_id: int, pest_name: str, phi_days: int | None, max_uses: int | None, use_suittime_raw: str | None, use_num_raw: str | None, dilut_raw: str | None, use_method: str | None, usage_type: Literal["NORMAL", "AT_PLANTING", "NO_LIMIT", "CHECK"], data_asof: date)`; `SprayRecord(id: int, pesticide_id: int, item_name: str, sprayed_on: date, moa: Moa | None)`; `JudgeInput(today: date, planted_at: date | None, history_confirmed: bool, pest_id: int | None, pesticide_id: int, item_name: str, moa: Moa | None, registrations: list[Registration], history: list[SprayRecord], psis_asof: date)`; `Evidence(source_text: str, data_asof: date)`; `CheckResult(key: Literal["registration", "timing", "count", "moa"], status: Verdict, message: str, facts: dict[str, Any], evidence: Evidence)`.
- Produces in `tests/judge_support.py`: `reg(**overrides) -> Registration` and `make_input(**overrides) -> JudgeInput`, both starting from the §9 `base` fixture: `today` 2026-10-04, `planted_at` 2026-05-01, `history_confirmed` True, `pest_id` 1, `pesticide_id` 10, `item_name` 「품목A」, `moa` `Moa("가1", "FRAC", "4")`, `history` [], `psis_asof` 2026-10-03, `registrations` = `[reg()]`; `reg()` = pest 1 「탄저병」, `phi_days` 7, `max_uses` 3, `use_suittime_raw` 「수확 7일 전까지」, `use_num_raw` 「3회 이내」, `dilut_raw` 「1000배」, `use_method` 「발생 초부터 경엽처리」, `usage_type` NORMAL, `data_asof` 2026-10-01.

- [ ] **Step 1: Write the failing tests** in `tests/test_judge_schemas.py`
```python
from datetime import date

import pytest
from pydantic import ValidationError

from app.judgment.domain.schemas import CheckResult, Evidence, Verdict
from tests.judge_support import make_input, reg


def test_verdict_values_are_the_spec_strings():
    assert [v.value for v in Verdict] == ["OK", "CAUTION", "BLOCKED", "NEEDS_CHECK"]


def test_check_result_serializes_to_the_spec_shape():
    result = CheckResult(
        key="registration",
        status=Verdict.OK,
        message="m",
        facts={"rows": 1},
        evidence=Evidence(source_text="없음", data_asof=date(2026, 10, 3)),
    )

    assert result.model_dump(mode="json") == {
        "key": "registration",
        "status": "OK",
        "message": "m",
        "facts": {"rows": 1},
        "evidence": {"source_text": "없음", "data_asof": "2026-10-03"},
    }


def test_unknown_usage_type_is_rejected():
    with pytest.raises(ValidationError):
        reg(usage_type="WEIRD")


def test_base_input_is_the_section_9_fixture():
    inp = make_input()

    assert (inp.today, inp.planted_at, inp.history_confirmed) == (
        date(2026, 10, 4), date(2026, 5, 1), True,
    )
    assert (inp.pest_id, inp.pesticide_id, inp.item_name) == (1, 10, "품목A")
    assert (inp.moa.label_kr, inp.moa.system, inp.moa.code) == ("가1", "FRAC", "4")
    assert (inp.history, inp.psis_asof) == ([], date(2026, 10, 3))
    [r] = inp.registrations
    assert (r.pest_id, r.pest_name, r.phi_days, r.max_uses) == (1, "탄저병", 7, 3)
    assert (r.use_suittime_raw, r.use_num_raw, r.dilut_raw) == ("수확 7일 전까지", "3회 이내", "1000배")
    assert (r.use_method, r.usage_type, r.data_asof) == (
        "발생 초부터 경엽처리", "NORMAL", date(2026, 10, 1),
    )
```
- [ ] **Step 2: Run** `.venv\Scripts\python -m pytest tests\test_judge_schemas.py -q` — Expected: collection ERROR `No module named 'app.judgment'`.
- [ ] **Step 3: Implement `schemas.py`** with the models above (a shared base class with `ConfigDict(frozen=True)`).
- [ ] **Step 4: Write `tests/judge_support.py`** (`reg`, `make_input` as specified; overrides replace the default values).
- [ ] **Step 5: Run** the step 2 command — Expected: `4 passed`; `.venv\Scripts\python -m pytest -q` and `.venv\Scripts\ruff check .` clean (wrap lines to 100 characters).
- [ ] **Step 6: Commit** `git add app/judgment tests/judge_support.py tests/test_judge_schemas.py` / `git commit -m "Add judgment domain types"`

### Task 2: ① registration

**Files:**
- Create: `app/judgment/domain/rules.py`
- Test: `tests/test_judge_registration.py`

**Interfaces:**
- Consumes: Task 1 types and `tests/judge_support.py`.
- Produces in `rules.py`: `considered_rows(inp: JudgeInput) -> list[Registration]` (registrations of `inp.pest_id`, all registrations when `pest_id` is None, input order kept); `rows_data_asof(inp: JudgeInput) -> date` (oldest `data_asof` of `considered_rows(inp)`, `inp.psis_asof` when there are none); `check_registration(inp: JudgeInput) -> CheckResult` (`key="registration"`, `evidence.data_asof = rows_data_asof(inp)`).

Cases, first match wins (judgment rules §4 ① and §8):

| Condition | status | message | facts | evidence.source_text |
|---|---|---|---|---|
| `registrations` empty | BLOCKED | 이 작물에는 등록되어 있지 않습니다 | `{crop_registered: False}` | 없음 |
| `pest_id` set, no considered rows | BLOCKED | 이 병해충에는 등록되어 있지 않습니다 (이 작물에 등록된 병해충 {n}종) | `{crop_registered: True, registered_pests}` | 등록 병해충: {names joined by ", "} |
| `pest_id` None | NEEDS_CHECK | 병해충을 지정하지 않아 등록 여부를 확인할 수 없습니다 (이 작물에는 등록되어 있습니다) | `{crop_registered: True, pest_specified: False, registered_pests}` | 등록 병해충: {names} |
| otherwise | OK | 이 병해충에 등록된 약제입니다 | `{pest_specified: True, rows: len(considered)}` | first considered row's `use_method` and `dilut_raw` that are not empty, joined by " · "; 없음 if none |

`registered_pests` = distinct `pest_name` of all `registrations`, sorted; `{n}` = its length.

- [ ] **Step 1: Write the failing tests** in `tests/test_judge_registration.py`
```python
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
        "crop_registered": True, "pest_specified": False, "registered_pests": ["탄저병"],
    }
    assert r.evidence.source_text == "등록 병해충: 탄저병"


def test_r5_pest_not_specified_and_nothing_registered():
    r = run(pest_id=None, registrations=[])

    assert r.status is Verdict.BLOCKED
    assert r.facts == {"crop_registered": False}


def test_r6_registered_pests_are_distinct_and_sorted():
    rows = [reg(**OTHER), reg(**OTHER, use_method="토양처리"), reg(pest_id=3, pest_name="겹둥근무늬병")]
    r = run(registrations=rows)

    assert r.message.endswith("(이 작물에 등록된 병해충 2종)")
    assert r.facts["registered_pests"] == ["겹둥근무늬병", "역병"]
    assert r.evidence.source_text == "등록 병해충: 겹둥근무늬병, 역병"


def test_r7_evidence_shows_only_what_exists():
    assert run(registrations=[reg(use_method=None, dilut_raw=None)]).evidence.source_text == "없음"
    assert run(registrations=[reg(use_method=None)]).evidence.source_text == "1000배"
    assert run(registrations=[reg(dilut_raw=None)]).evidence.source_text == "발생 초부터 경엽처리"


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
```
- [ ] **Step 2: Run** `.venv\Scripts\python -m pytest tests\test_judge_registration.py -q` — Expected: collection ERROR `No module named 'app.judgment.domain.rules'`.
- [ ] **Step 3: Implement** `considered_rows`, `rows_data_asof` and `check_registration` in `rules.py` per the table above.
- [ ] **Step 4: Run** the step 2 command — Expected: `8 passed`; full suite and `ruff check .` clean.
- [ ] **Step 5: Commit** `git add app/judgment/domain/rules.py tests/test_judge_registration.py` / `git commit -m "Add registration check"`

### Task 3: ② timing

**Files:**
- Modify: `app/judgment/domain/rules.py`
- Test: `tests/test_judge_timing.py`, `tests/test_judge_domain_rules.py`

**Interfaces:**
- Consumes: `considered_rows`, `rows_data_asof`, `check_registration` (Task 2), types (Task 1).
- Produces in `rules.py`: `calc_rows(rows: list[Registration]) -> list[Registration]` (drop `AT_PLANTING` rows, then `NO_LIMIT` rows, each step only if rows remain afterwards; order kept); `format_date_kr(d: date, today: date) -> str`; `check_timing(inp: JudgeInput, registration: CheckResult) -> CheckResult` (`key="timing"`, `evidence.data_asof = rows_data_asof(inp)`).

Cases of `check_timing`, first match wins (judgment rules §3, §4 ②, §8). `rows = considered_rows(inp)`, `calc = calc_rows(rows)`; a row's number is NULL when `phi_days` is None **or** `usage_type == "CHECK"`; the "unreadable row" is the first row of `calc` with a NULL number; `{raw}` = its `use_suittime_raw`, 「없음」 if empty. `facts` always has all five keys; unless stated, `phi_days`, `harvest_from`, `strict_use_method` are None, `rows` = `len(rows)`, `no_limit` False.

| Condition | status | message | evidence.source_text |
|---|---|---|---|
| `registration.status` is BLOCKED (`rows` is 0) | NEEDS_CHECK | 등록 정보가 없어 확인할 수 없습니다 | 없음 |
| every row of `calc` is `AT_PLANTING` | NEEDS_CHECK | 이 약은 심을 때(정식기·파종기) 쓰는 약입니다. 수확 전 사용 기준이 없어 수확 가능일을 계산할 수 없습니다. 원문: {raw} | {raw} |
| some row of `calc` has a NULL number | NEEDS_CHECK | 수확 전 사용 기준을 읽지 못했습니다. 원문: {raw} | {raw} |
| every row of `calc` is `NO_LIMIT` | OK | 수확 전 사용 일수 제한이 없는 약제입니다. 라벨의 사용 방법을 확인해 주세요 | first `calc` row's `use_suittime_raw` (없음 if empty); `no_limit` True |
| `phi` = max `phi_days` of `calc` is 0 | OK | 수확 당일까지 사용할 수 있습니다 | strict row's `use_suittime_raw` |
| `phi` ≥ 1 | OK | 오늘 살포하면 {format_date_kr(today + phi days)}부터 수확할 수 있습니다 (수확 {phi}일 전까지 사용) | strict row's `use_suittime_raw` |

The strict row is the first `calc` row with `phi_days == phi`; `facts` = `phi_days` phi, `harvest_from` ISO date of `today + phi days`, `strict_use_method` = strict row's `use_method`. When `calc` has two or more distinct non-empty `use_method` values and the strict row's `use_method` is not empty, the two OK messages with a strict row end with ` ({use_method} 기준)`.

- [ ] **Step 1: Write the failing tests.** `tests/test_judge_timing.py`:
```python
from datetime import date

import pytest

from app.judgment.domain.rules import check_registration, check_timing
from app.judgment.domain.schemas import Verdict
from tests.judge_support import make_input, reg

OTHER = dict(pest_id=2, pest_name="역병")
OK, NEEDS_CHECK = Verdict.OK, Verdict.NEEDS_CHECK


def timing(**kw):
    inp = make_input(**kw)
    return check_timing(inp, check_registration(inp))


def facts(phi=None, harvest=None, rows=1, method=None, no_limit=False):
    return {
        "phi_days": phi, "harvest_from": harvest, "rows": rows,
        "strict_use_method": method, "no_limit": no_limit,
    }


def unreadable(raw):
    return f"수확 전 사용 기준을 읽지 못했습니다. 원문: {raw}"


def test_t1_base():
    r = timing()

    assert (r.key, r.status) == ("timing", OK)
    assert r.message == "오늘 살포하면 10월 11일부터 수확할 수 있습니다 (수확 7일 전까지 사용)"
    assert r.facts == facts(7, "2026-10-11", 1, "발생 초부터 경엽처리")
    assert r.evidence.source_text == "수확 7일 전까지"
    assert r.evidence.data_asof == date(2026, 10, 1)


def test_t2_phi_zero_is_harvest_day():
    r = timing(registrations=[reg(phi_days=0)])

    assert (r.status, r.message) == (OK, "수확 당일까지 사용할 수 있습니다")
    assert r.facts == facts(0, "2026-10-04", 1, "발생 초부터 경엽처리")


def test_t3_unreadable_phi_shows_the_raw_text():
    r = timing(registrations=[reg(phi_days=None, use_suittime_raw="수확 직전")])

    assert (r.status, r.message) == (NEEDS_CHECK, unreadable("수확 직전"))
    assert r.facts == facts()
    assert r.evidence.source_text == "수확 직전"


def test_t4_no_pest_uses_all_rows_and_the_strictest():
    rows = [reg(phi_days=7), reg(**OTHER, phi_days=14)]
    r = timing(pest_id=None, registrations=rows)

    assert r.status is OK
    assert r.facts == facts(14, "2026-10-18", 2, "발생 초부터 경엽처리")


def test_t5_other_pests_rows_are_ignored():
    rows = [reg(phi_days=7), reg(phi_days=10), reg(**OTHER, phi_days=30)]
    r = timing(registrations=rows)

    assert r.facts == facts(10, "2026-10-14", 2, "발생 초부터 경엽처리")


def test_t6_one_unreadable_row_makes_it_needs_check():
    r = timing(registrations=[reg(phi_days=7), reg(phi_days=None)])

    assert r.status is NEEDS_CHECK
    assert r.facts == facts(rows=2)


def test_t7_date_text_crosses_the_year():
    r = timing(today=date(2026, 12, 25), registrations=[reg(phi_days=14)])

    assert r.message == "오늘 살포하면 2027년 1월 8일부터 수확할 수 있습니다 (수확 14일 전까지 사용)"
    assert r.facts["harvest_from"] == "2027-01-08"


def test_t8_all_no_limit():
    r = timing(registrations=[reg(usage_type="NO_LIMIT", phi_days=None, use_suittime_raw="발생초기")])

    assert (r.status, r.message) == (
        OK, "수확 전 사용 일수 제한이 없는 약제입니다. 라벨의 사용 방법을 확인해 주세요",
    )
    assert r.facts == facts(no_limit=True)
    assert r.evidence.source_text == "발생초기"


def test_t9_all_at_planting():
    r = timing(registrations=[reg(usage_type="AT_PLANTING", phi_days=None, use_suittime_raw="정식기")])

    assert r.status is NEEDS_CHECK
    assert r.message == (
        "이 약은 심을 때(정식기·파종기) 쓰는 약입니다. 수확 전 사용 기준이 없어 "
        "수확 가능일을 계산할 수 없습니다. 원문: 정식기"
    )
    assert r.evidence.source_text == "정식기"


def test_t10_planting_row_is_left_out_of_the_calculation():
    rows = [reg(usage_type="AT_PLANTING", phi_days=None, use_suittime_raw="정식기"), reg(phi_days=7)]
    r = timing(registrations=rows)

    assert (r.status, r.facts["phi_days"], r.facts["rows"]) == (OK, 7, 2)


def test_t11_no_limit_row_is_left_out_of_the_calculation():
    rows = [reg(phi_days=7), reg(usage_type="NO_LIMIT", phi_days=None)]
    r = timing(registrations=rows)

    assert (r.status, r.facts["phi_days"], r.facts["no_limit"]) == (OK, 7, False)


def test_t12_check_row_without_numbers():
    r = timing(registrations=[reg(usage_type="CHECK", phi_days=None, use_suittime_raw="수확7일")])

    assert (r.status, r.message) == (NEEDS_CHECK, unreadable("수확7일"))


def test_t13_strictest_use_method_is_named():
    rows = [reg(phi_days=14, use_method="경엽처리"), reg(phi_days=21, use_method="무인항공")]
    r = timing(registrations=rows)

    assert r.facts == facts(21, "2026-10-25", 2, "무인항공")
    assert r.message == (
        "오늘 살포하면 10월 25일부터 수확할 수 있습니다 (수확 21일 전까지 사용) (무인항공 기준)"
    )


def test_t14_planting_row_goes_first_then_only_no_limit_remains():
    rows = [
        reg(usage_type="AT_PLANTING", phi_days=None),
        reg(usage_type="NO_LIMIT", phi_days=None, use_suittime_raw="발생초기"),
    ]
    r = timing(registrations=rows)

    assert (r.status, r.facts["no_limit"], r.evidence.source_text) == (OK, True, "발생초기")


def test_t15_check_row_with_numbers_is_still_unreadable():  # 실제 데이터 use_id 3539
    r = timing(registrations=[reg(usage_type="CHECK", phi_days=50, use_suittime_raw="수확50일전")])

    assert (r.status, r.message) == (NEEDS_CHECK, unreadable("수확50일전"))
    assert r.facts == facts()


def test_t16_raw_text_is_the_first_unreadable_rows_and_none_when_empty():
    rows = [reg(phi_days=None, use_suittime_raw="A"), reg(phi_days=None, use_suittime_raw="B")]
    assert timing(registrations=rows).evidence.source_text == "A"

    r = timing(registrations=[reg(phi_days=None, use_suittime_raw=None)])
    assert r.message == unreadable("없음")
    assert r.evidence.source_text == "없음"


def test_t17_equal_phi_picks_the_first_row_and_names_both_methods_apart():
    rows = [reg(phi_days=7, use_method="경엽처리"), reg(phi_days=7, use_method="무인항공")]
    r = timing(registrations=rows)

    assert r.facts["strict_use_method"] == "경엽처리"
    assert r.message.endswith("(경엽처리 기준)")


def test_t18_one_use_method_adds_no_suffix():
    rows = [reg(phi_days=7), reg(phi_days=10)]

    assert not timing(registrations=rows).message.endswith("기준)")


@pytest.mark.parametrize("kw", [{"registrations": [reg(**OTHER)]}, {"registrations": []}])
def test_blocked_registration_makes_timing_needs_check(kw):  # R2, R3의 ② 부분
    r = timing(**kw)

    assert (r.status, r.message) == (NEEDS_CHECK, "등록 정보가 없어 확인할 수 없습니다")
    assert r.facts == facts(rows=0)
    assert r.evidence.source_text == "없음"
    assert r.evidence.data_asof == date(2026, 10, 3)
```
`tests/test_judge_domain_rules.py` (helpers, date text, message scan, purity):
```python
from datetime import date
from pathlib import Path

import pytest

from app.judgment.domain.rules import calc_rows, check_registration, check_timing, format_date_kr
from tests.judge_support import make_input, reg

FORBIDDEN = ["추천", "예측", "예상", "가능성", "위험", "확률", "안전", "문제없"]
DOMAIN = Path(__file__).resolve().parents[1] / "app" / "judgment" / "domain"
OTHER = dict(pest_id=2, pest_name="역병")


@pytest.mark.parametrize(
    "types,kept",
    [
        (["AT_PLANTING", "NORMAL"], [1]),
        (["NORMAL", "NO_LIMIT"], [0]),
        (["AT_PLANTING", "NO_LIMIT"], [1]),
        (["AT_PLANTING", "AT_PLANTING"], [0, 1]),
        (["NO_LIMIT", "NO_LIMIT"], [0, 1]),
        (["AT_PLANTING", "NO_LIMIT", "NORMAL"], [2]),
        (["AT_PLANTING", "CHECK"], [1]),
    ],
)
def test_calc_rows_drops_planting_then_no_limit_only_while_rows_remain(types, kept):
    rows = [reg(usage_type=t, use_method=f"m{i}") for i, t in enumerate(types)]

    assert [r.use_method for r in calc_rows(rows)] == [f"m{i}" for i in kept]


def test_format_date_kr():
    assert format_date_kr(date(2026, 10, 11), today=date(2026, 10, 4)) == "10월 11일"
    assert format_date_kr(date(2027, 1, 8), today=date(2026, 12, 25)) == "2027년 1월 8일"


SCAN_INPUTS = [
    {},
    {"registrations": [reg(**OTHER)]},
    {"registrations": []},
    {"pest_id": None},
    {"registrations": [reg(phi_days=0)]},
    {"registrations": [reg(phi_days=None)]},
    {"registrations": [reg(usage_type="NO_LIMIT", phi_days=None)]},
    {"registrations": [reg(usage_type="AT_PLANTING", phi_days=None)]},
    {"registrations": [reg(phi_days=14, use_method="경엽처리"), reg(phi_days=21, use_method="무인항공")]},
    {"today": date(2026, 12, 25), "registrations": [reg(phi_days=14)]},
]


def test_no_forbidden_word_in_any_registration_or_timing_message():
    for kw in SCAN_INPUTS:
        inp = make_input(**kw)
        registration = check_registration(inp)
        for result in (registration, check_timing(inp, registration)):
            assert not [w for w in FORBIDDEN if w in result.message], result.message


def test_domain_imports_no_db_http_or_clock():
    text = "".join(p.read_text(encoding="utf-8") for p in DOMAIN.glob("*.py"))

    for word in ("sqlalchemy", "fastapi", "httpx", "datetime.now", "date.today"):
        assert word not in text
```
- [ ] **Step 2: Run** `.venv\Scripts\python -m pytest tests\test_judge_timing.py tests\test_judge_domain_rules.py -q` — Expected: collection ERROR `cannot import name 'check_timing'` (and `calc_rows`, `format_date_kr`).
- [ ] **Step 3: Implement** `calc_rows`, `format_date_kr` and `check_timing` in `rules.py` per the table above.
- [ ] **Step 4: Run** the step 2 command — Expected: `30 passed` (20 in `test_judge_timing.py`: T1–T18 plus the 2 blocked cases; 10 in `test_judge_domain_rules.py`: 7 `calc_rows`, 1 date, 1 message scan, 1 purity guard). Full suite and `ruff check .` clean (wrap long lines to 100).
- [ ] **Step 5: Commit** `git add app/judgment/domain/rules.py tests/test_judge_timing.py tests/test_judge_domain_rules.py` / `git commit -m "Add timing check"`
- [ ] **Step 6: Mutation check.** In `rules.py` change `calc_rows` to drop `NO_LIMIT` before `AT_PLANTING`, run `tests\test_judge_timing.py tests\test_judge_domain_rules.py` — Expected: `test_calc_rows_drops_planting_then_no_limit_only_while_rows_remain` FAILS (and at least one T-case); restore with `git checkout -- app/judgment/domain/rules.py`; re-run — `30 passed`; `git status --short` clean.

### Task 4: Final verification

- [ ] **Step 1:** `.venv\Scripts\python -m pytest -q -rs` and `.venv\Scripts\ruff check .` — Expected: all pass, `All checks passed!`.
- [ ] **Step 2:** `git diff --name-only origin/test..HEAD` lists no `팜가디언_API_명세.md`; `git status -sb` clean; `git log --oneline origin/test..HEAD` shows 4 commits. Do not push.
- [ ] **Step 3:** Tell the user: BE-38/39 done at domain level; open items for BE-42 (verdict, notices, `JudgeResult.data_asof`, the `verdict`/`notices` parts of R2, R4, R5) and BE-45 (row mapping per the design).
