# BE-49 Wording Scan and E2E Smoke Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (project CLAUDE.md: no subagent-driven execution). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the two gaps of BE-49 (「e2e 테스트·문구 점검」): every user-facing judgment template is checked against the forbidden words, and one test walks the user scenario across all contexts through the real API.

**Architecture:** Two new test files, no app code. `tests/test_judgment_wording.py` scans the Korean string literals of the judgment code with `ast`. `tests/test_e2e_scenario.py` is one test on the PostGIS test DB with a small fake Farmmap, calling only the HTTP API (plus one SQL line where an endpoint does not exist yet).

**Tech Stack:** Python 3.13, pytest, `ast`, FastAPI `TestClient`, the existing `client` and `db` fixtures from `tests/conftest.py`.

**Spec:** Approved in chat 2026-10-30. Basis: `팜가디언_아키텍처.md` §9 (「문구 검사」, 「e2e 스모크 1개」), `팜가디언_판정_규칙.md` §8 (forbidden words, scope = judgment wording only).

## Global Constraints

- **No file of Hyebin's is modified** (`app/farm/**`, her tests, `tests/farm_support.py`, her documents). Her split-preview and zone-creation endpoints are only called. Check at the end: `git diff origin/test -- app tests/farm_support.py` shows nothing.
- No change to `app/`, `schema.sql`, `팜가디언_API_명세.md` or `requirements*.txt`; no new dependency. The two existing forbidden-word tests stay untouched.
- Forbidden words (from judge rules §8), exactly: `추천`, `예측`, `예상`, `가능성`, `위험`, `확률`, `안전`, `문제없`. The scan covers judgment wording only (`rules.py`, `service.py`); weather terms such as 「강수확률」 are out of scope.
- The wording scan reads Korean string literals only (docstrings and comments excluded) and must never pass vacuously: known templates have to be among the scanned literals.
- The e2e test must not depend on catalog specifics a data refresh could change: no brand names, no fixed ids. Data comes from the helpers in `tests/judgment_scenarios.py` (`pest_with_alternatives`, `unregistered_drug`, `pool`) and the catalog service.
- The e2e uses its own small fake Farmmap inside the test file (it only imports the `FarmmapParcel` dataclass read-only), so it does not depend on Hyebin's test helper.
- Not covered because the endpoints do not exist yet: weather, `GET /zones/{id}`, `PATCH /zones/{id}`. 「누락 없음」 is set with one SQL `UPDATE` and marked with a comment to switch to the API later.
- Code and identifiers in English, short Korean comments like the surrounding tests; ruff line length 100 (Korean counts double); tests flat in `tests/`; commit messages in English with the session's attribution trailer; do not push; stage explicit paths only (the working tree has an unrelated uncommitted backlog xlsx, `.gitignore` change and an untracked scenario document). Branch `feat/jh-be49-tests` from `test` at `0782fa0`.

## Review Focus

- The scanner is not vacuous: it finds known templates (a registration message, `NO_ALTERNATIVE_NOTICE`, the 「작용기작 미상」 tail) and flags a forbidden literal in a synthetic source. (Task 1)
- Putting a forbidden word into a real template makes the repo scan fail (mutation check, restored afterwards). (Task 1)
- The e2e leaves no rows behind and ends with the withdrawn user answering 401. (Task 2)
- The e2e survives a catalog refresh: no brand names, no fixed ids. (Task 2)
- No file of Hyebin's changed. (Task 3)

---

### Task 0: Branch and commit this plan

- [ ] **Step 1:** `git switch -c feat/jh-be49-tests` (from `test`; unrelated uncommitted and untracked files stay as they are).
- [ ] **Step 2:** `git add docs/dev/2026-10-30-be49-tests-plan.md` / `git commit -m "Add BE-49 tests plan"`.

### Task 1: Wording scan over every template

**Files:**
- Create: `tests/test_judgment_wording.py`

**Interfaces:**
- Produces (inside the test file): `korean_literals(source: str) -> list[tuple[int, str]]`, the `(line, text)` of every `str` constant that contains a Hangul syllable, with docstrings left out and the constant parts of f-strings included; `forbidden_in(literals) -> list[tuple[int, str, str]]` returning `(line, word, text)` for each hit.

- [ ] **Step 1: Write the tests** in `tests/test_judgment_wording.py` (reads `app/judgment/domain/rules.py` and `app/judgment/application/service.py` relative to the repo root):
  - `test_no_template_contains_a_forbidden_word`: for both files, `forbidden_in(korean_literals(text))` is empty; the assertion message lists file, line, word and literal.
  - `test_the_scan_sees_the_known_templates`: among the scanned literals of `rules.py` there is one containing `이 병해충에 등록된 약제입니다` and one containing `작용기작 미상`; among those of `service.py` one containing `병해충을 지정하면 대안을 볼 수 있습니다`; and the total scanned literals are more than 40 (62 today).
  - `test_the_scanner_flags_a_forbidden_literal`: `forbidden_in(korean_literals("x = '이 약은 안전합니다'"))` has one hit with word `안전`; the same word only in a docstring (`def f():\n    """안전"""`) or a comment gives none; an f-string such as `f"위험 {n}"` is flagged.
  - `test_every_forbidden_word_is_detected`: for each of the eight words, a synthetic literal containing it is flagged.
- [ ] **Step 2:** `pytest tests/test_judgment_wording.py -v` → all pass at once (the repo is clean, 0 hits). Then the mutation check: temporarily change one template in `app/judgment/domain/rules.py` to contain `안전` (for example the registration message), run the first test and see it **fail naming that line**; restore the file with `git checkout -- app/judgment/domain/rules.py` and confirm `git diff --stat -- app` is empty.
- [ ] **Step 3:** `pytest tests/test_judgment_wording.py -q` passes again; `ruff check tests/test_judgment_wording.py` clean.
- [ ] **Step 4:** `git add tests/test_judgment_wording.py` / `git commit -m "Scan every judgment template for forbidden words"`.

### Task 2: One e2e smoke test

**Files:**
- Create: `tests/test_e2e_scenario.py`

**Interfaces:**
- Consumes: fixtures `client`, `db`; `catalog_service.list_pesticides(crop_id)`; `tests.judgment_scenarios.pest_with_alternatives(2)`, `unregistered_drug(2)`, `pool(2, pest)`; `FarmmapParcel` from `app.farm.infrastructure.integrations.farmmap`.
- Produces: nothing for other tasks.

- [ ] **Step 1: Write the test** `test_the_user_scenario_end_to_end(client, db, monkeypatch)`. A fake `farmmap.parcel_by_id` (monkeypatched, signature `(farmmap_id, *, client=None)`) returns a 10 x 10 square for ids `"1"` and `"2"` placed side by side (a 20 x 10 field). Each step asserts status and the spec's shape, with a short message naming the step; all calls use the `X-User-Id` returned by signup:
  1. `POST /auth/signup` with parcels `["1", "2"]` → 201 `{id, username, field}`, `field.zones == []`, `field.area_m2` near 200; `GET /me` → `onboarded` false; `GET /crops` → 3 crops.
  2. `POST /fields/{id}/split-preview` `{direction: "crosswise", ratios: [6, 4]}` → 200 with 2 pieces whose `area_m2` sum is close to the field's; `POST /fields/{id}/zones` with names `A구역` (crop 2, `planted_at` `2026-09-10`) and `B구역` (crop 1) → 201 with 2 zones (spec `Zone` keys).
  3. Past sprays on zone A: two drugs of crop 2 taken from `catalog_service.list_pesticides(2)` that are **not** in `pool(2, pest)` for `pest = pest_with_alternatives(2)`, dated `2026-10-01` and `2026-10-05`, each with a fresh `request_id` → 201; `GET /zones/{A}/sprays` → total 2; `DELETE` one → 204 and total 1; add it again → 201 and total 2.
  4. `POST /me/onboarding` → 422 `ONBOARDING_INCOMPLETE` with both zone ids in `unconfirmed_zone_ids`; set `history_confirmed = true` on both zones with one SQL `UPDATE` through `db` (comment: switch to `PATCH /zones/{id}` when it exists); `POST /me/onboarding` → 200, `GET /me` → `onboarded` true; `GET /fields` → zone A's `last_spray` is not null and zone B's is null.
  5. Picking a pest: `GET /crops/2/symptom-parts` non-empty; `GET /pests/candidates` for the first part non-empty; `GET /pests?crop_id=2` contains `pest`; `GET /pesticides?crop_id=2&pest_id={pest}` non-empty.
  6. `POST /zones/{A}/judgments` with `unregistered_drug(2)` and `pest` → 201, 4 checks in the order registration, timing, count, moa, verdict `BLOCKED`, `alternatives` non-empty with `moa` set and every alternative's `moa.label_kr` different from the chosen drug's (when it has one); no spray was created by the judgment (spray total unchanged).
  7. Save a spray with the first alternative: 201; the same drug and date again → 409 `DUPLICATE_SPRAY` with `details.existing.id` equal to the first one; the first request sent again with its `request_id` → 200 and the same id.
  8. `DELETE /fields/{id}` → 204; `GET /fields` → `[]`; `GET /zones/{A}/sprays` → 404.
  9. `DELETE /me` → 204; `GET /me` with the same header → 401; a SQL count shows no `users` row with that id.
- [ ] **Step 2:** `pytest tests/test_e2e_scenario.py -v` → passes; if a step fails, the message names the step. Run it three times in a row (the fixture rolls back) to confirm it leaves nothing behind: `SELECT count(*) FROM users` through a fresh connection is the same before and after.
- [ ] **Step 3:** Robustness check: monkeypatch nothing else, but run `pytest tests/test_e2e_scenario.py -q -p no:randomly` and confirm there are no hard-coded brand names or ids in the file: `grep -nE "알칸타|엑시렐" tests/test_e2e_scenario.py` prints nothing; `ruff check tests/test_e2e_scenario.py` clean.
- [ ] **Step 4:** `git add tests/test_e2e_scenario.py` / `git commit -m "Add one e2e smoke test of the user scenario"`.

### Task 3: Verify everything

- [ ] **Step 1:** `pytest -q -rs` → every test passes, none skipped; `ruff check .` → `All checks passed!`.
- [ ] **Step 2:** `git diff origin/test -- app tests/farm_support.py` → no output; `git diff --stat origin/test` lists only the plan and the two new test files (plus the unrelated uncommitted files, which are not part of the branch).
- [ ] **Step 3:** Report: the commands and output, what the scan covers (62 Korean template literals today), the mutation check result, that the e2e calls but does not change Hyebin's endpoints, and that after the merge the backlog row BE-49 can be ticked (xlsx edit only while Excel is closed). Push and PR wait for the user's word.
