# Verdict wording and 「심을 때」 status Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (inline, per CLAUDE.md). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Judgment sentences read in 「~어요」, the raw label text sits on its own line, and planting-time drugs / unplanted zones show the 「심을 때」 status.

**Architecture:** The backend changes only message strings and adds one facts key (`reason`) on timing/count `NEEDS_CHECK`. The frontend maps that key to the 「심을 때」 status and the raw-text line. Living docs are updated in the same commits as the code they describe.

**Tech Stack:** Python 3.13 / pytest / ruff (backend), React + TypeScript (frontend, no test runner; `npx tsc --noEmit`).

**Spec:** `docs/dev/2026-11-04-verdict-wording-design.md`

## Global Constraints

- Only sentence endings change; vocabulary stays (design §Backend table is the exact new text).
- Statuses, existing facts keys and `evidence` stay the same; `facts.reason` is additive and present only on timing/count `NEEDS_CHECK`.
- Forbidden words (`추천 예측 예상 가능성 위험 확률 안전 문제없`) must stay out of judgment templates.
- Error messages (`AppError`) are out of scope.
- Dated design/plan docs (`docs/dev/2026-10-*`, `2026-11-0[12]-*`) are historical records and are not edited. Living docs that are edited: `팜가디언_판정_규칙.md`, `팜가디언_API_명세.md`, `팜가디언_PRD_수정_제안.md` (the notice quote).
- Commits in English, no AI attribution. Backend PR → `test`, frontend PR → `main`, Korean PR bodies starting with 「관련 이슈: #N」.

## Review Focus

- ③ count `NEEDS_CHECK` for no planting date / unconfirmed history must **not** show a 「원문」 line → covered by `reason` tests in Task 1 (those branches get `no_planting` / `unconfirmed`, not `unreadable`).
- ① `BLOCKED` drug that is also at-planting must still show 불가 → Task 1 asserts `reason = "not_registered"` (not `at_planting`) when ① is BLOCKED; Task 3 keeps priority 불가 > 심을 때.
- A suffix (「(무인항공 기준)」, 「(작용기작 미상 N건 포함)」) after a changed ending must still attach → existing suffix tests in Task 2 are updated, not deleted.
- 「니다」 sneaking back into a template → guard test in Task 2.
- OK checks must not carry `reason` → Task 1 asserts `"reason" not in facts` for an OK timing and count.

---

### Task 1: Backend `facts.reason` on timing/count `NEEDS_CHECK`

**Files:**
- Modify: `app/judgment/domain/rules.py` (`check_timing` NEEDS_CHECK returns ~L139-157, `check_count` ~L366-390)
- Test: `tests/test_judge_timing.py`, `tests/test_judge_count.py`
- Docs: `docs/dev/팜가디언_판정_규칙.md` (§5 timing facts line ~155, count facts line ~173), `docs/dev/팜가디언_API_명세.md` (facts table rows `timing`, `count` ~L287-288)

**Interfaces:**
- Produces: `CheckResult.facts["reason"]` ∈ timing {`not_registered`, `at_planting`, `unreadable`}, count {`not_registered`, `unreadable`, `no_planting`, `unconfirmed`}; key absent when status ≠ `NEEDS_CHECK`. The frontend (Task 3) relies on these exact strings.

- [ ] **Step 0:** `git switch test && git pull --ff-only && git switch -c fix/hb-verdict-wording`
- [ ] **Step 1: Write failing tests** in the existing files next to the matching branch tests:
  - timing: at-planting case (T9) → `r.facts["reason"] == "at_planting"`; unreadable (T3) → `"unreadable"`; ① BLOCKED → `"not_registered"`; base OK (T1) → `"reason" not in r.facts`.
  - count: unreadable (C11) → `"unreadable"`; `planted_at=None` (C6) → `"no_planting"`; unconfirmed (C9) → `"unconfirmed"`; ① BLOCKED → `"not_registered"`; base OK → `"reason" not in r.facts`.
- [ ] **Step 2:** `.venv/Scripts/python -m pytest tests/test_judge_timing.py tests/test_judge_count.py -q` → the new tests FAIL (KeyError / assertion).
- [ ] **Step 3: Implement** by passing `reason="…"` through the existing `result(..., **facts)` helpers at each `NEEDS_CHECK` return. No other change.
- [ ] **Step 4:** same pytest command → PASS.
- [ ] **Step 5: Docs.** 판정 규칙 §5: append to both facts lines 「`NEEDS_CHECK`일 때만 `reason`(…값 목록…)이 붙는다」. API 명세: add `reason?: "not_registered"|"at_planting"|"unreadable"` to `timing` and `reason?: "not_registered"|"unreadable"|"no_planting"|"unconfirmed"` to `count`.
- [ ] **Step 6: Commit** the design and this plan first (`git commit -m "Plan the verdict wording and planting-time status"`), then the code (`git commit -m "Add facts.reason to timing and count NEEDS_CHECK results"`)

### Task 2: Backend messages in 「~어요」, no 「원문」 in messages

**Files:**
- Modify: `app/judgment/domain/rules.py` (constants L20-26 and every message literal), `app/judgment/application/service.py:25` (`NO_ALTERNATIVE_NOTICE` only)
- Test: `tests/test_judge_count.py`, `tests/test_judge_moa.py`, `tests/test_judge_registration.py`, `tests/test_judge_result.py`, `tests/test_judge_timing.py`, `tests/test_judgment_api.py`, `tests/test_judgment_assess.py`, `tests/test_judgment_sweep.py`, `tests/test_judgment_wording.py`
- Docs: `docs/dev/팜가디언_판정_규칙.md` (§5 L148-149, §6 notices L207-209, §8 table L241-265 and the `{raw}` note L271, §9 rows quoting messages: R1-R4, T1-T3, T7-T9, T12, T16, C4, C6, C9, C11, C18, M1-M5, M7, M10, S2, and any other 「…니다」 quote of a template), `docs/dev/팜가디언_PRD_수정_제안.md:15`

**Interfaces:**
- Consumes: nothing new.
- Produces: the exact strings in the design's §Backend table (the frontend shows them as-is).

- [ ] **Step 1: Update tests to the new text first.** Every expected string in the test files above becomes the design table's new text; the unreadable helpers drop the suffix (`test_judge_timing.py:31` → `"수확 전 사용 기준을 읽지 못했어요"`, `test_judge_count.py:45` → `"최대 사용 횟수 기준을 읽지 못했어요"`), and the at-planting expectation (`test_judge_timing.py:107-108`) becomes `"이 약은 심을 때(정식기·파종기) 쓰는 약이에요. 수확 전 사용 기준이 없어 수확 가능일을 계산할 수 없어요"`. Where the unreadable/at-planting tests previously only saw the raw text in the message, add `assert r.evidence.source_text == <raw>` so the raw text is still pinned.
- [ ] **Step 2: Add the guard test** to `tests/test_judgment_wording.py`:
  ```python
  def test_templates_use_haeyo_endings():
      hits = [(line, text) for line, text in _literals("rules") if "니다" in text]
      assert not hits, hits
      from app.judgment.application.service import NO_ALTERNATIVE_NOTICE
      assert "니다" not in NO_ALTERNATIVE_NOTICE
  ```
  and change `test_the_scan_sees_the_known_templates` to look for `"이 병해충에 등록된 약제예요"` and `"병해충을 지정하면 대안을 볼 수 있어요"`.
- [ ] **Step 3:** `.venv/Scripts/python -m pytest tests/test_judg* -q` → many FAIL on the old text.
- [ ] **Step 4: Implement** the design table in `rules.py` and `service.py` (endings only; drop `원문: {raw}` from the three messages; keep `raw` as `source_text`).
- [ ] **Step 5:** `.venv/Scripts/python -m pytest -q` and `.venv/Scripts/ruff check .` → all pass.
- [ ] **Step 6: Docs** as listed in Files; the §8 `{raw}` note becomes 「원문은 문구에 넣지 않고 `evidence.source_text`로만 보낸다」, and fix the stray 「1|」 at the start of the §8 at-planting row. Then `Grep` the three living docs for `니다」` quotes of templates to confirm none remain.
- [ ] **Step 7: Commit** `git commit -m "Write judgment messages in the -eoyo style and keep raw text in evidence only"`

### Task 3: Frontend 「심을 때」 status and raw-text line

Repo `D:\farmguardian-FE`. Leave the user's unrelated `package-lock.json` change unstaged.

**Files:**
- Modify: `src/lib/verdict.ts` (types `Check`, `Verdict`), `src/lib/serverVerdict.ts` (`ServerCheck`, `toVerdict`), `src/screens/Verdict.tsx` (hero, `CheckCell`, cta note), `src/screens/Verdict.css` (`.check__source`)

**Interfaces:**
- Consumes: Task 1 `facts.reason` strings; `evidence.source_text`.
- Produces: `Check.stateLabel?: string`, `Check.source?: string`, `Verdict.atPlanting?: boolean`.

- [ ] **Step 0:** `git switch main && git pull --ff-only && git switch -c fix/hb-verdict-wording`
- [ ] **Step 1: Types.** `ServerCheck` gains `evidence: { source_text: string }`. `Check` gains `stateLabel?: string; source?: string`. `Verdict` gains `atPlanting?: boolean`.
- [ ] **Step 2: `toVerdict`** per check, from `c.facts.reason`:
  - timing + `at_planting` → `status: 'preplant'`, `stateLabel: '심을 때'`, `source: c.evidence.source_text`
  - timing/count + `unreadable` → keep `unknown`, `source: c.evidence.source_text`
  - count + `no_planting` → `status: 'preplant'` (label stays STATUS_META 「심기 전」)
  - `atPlanting` = timing reason is `at_planting`. Overall status keeps the existing PRIORITY sort (불가 > 심을 때 > …). Update the stale comment at L27.
- [ ] **Step 3: `Verdict.tsx`.**
  - headline: `v.atPlanting && v.status === 'preplant' ? '심을 때 쓰는 약이에요' : meta.headline`
  - 「심은 날 입력하기」 link only when `v.status === 'preplant' && !v.atPlanting`
  - cta note for preplant: `v.atPlanting ? '심을 때 쓰는 약은 여기서 기록할 수 없어요' : '심은 뒤에 기록할 수 있어요'`
  - `CheckCell`: state text `c.stateLabel ?? m.check`; after `{c.text}` render `{c.source && <span className="check__source">원문: {c.source}</span>}`
- [ ] **Step 4: CSS** in `Verdict.css`: `.check__source { display: block; margin-top: var(--sp-1); font-size: var(--fs-xs); color: var(--text-3); }` (use the nearest existing size/spacing tokens if these names differ).
- [ ] **Step 5:** `npx tsc --noEmit` (Hyebin runs it if blocked for Claude) → no output.
- [ ] **Step 6: Commit** `git commit -m "fix: show the planting-time status and the raw label text on the verdict screen"`

### Task 4: End-to-end check and PRs

- [ ] **Step 1:** Restart the backend (`uvicorn app.main:app --reload` picks it up) and reload the frontend. On 감자밭 → 가루더뎅이병 → 엑사이도 confirm: badge 「심을 때」, headline 「심을 때 쓰는 약이에요」, timing card 「심을 때」 + sentence + separate 「원문: 정식기」, all check sentences end in 「~어요」, no 「심은 날 입력하기」 link, note 「심을 때 쓰는 약은 여기서 기록할 수 없어요」. A normal drug shows no 「원문」 line.
- [ ] **Step 2:** `superpowers:verification-before-completion`: backend `pytest -q` + `ruff check .` output, frontend `tsc` result.
- [ ] **Step 3:** Push both branches; create one issue per repo and the two PRs (Korean body: 요약 / 변경 사항 / 테스트, note the merge-order section of the design).
