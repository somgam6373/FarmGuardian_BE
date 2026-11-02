# Frontend integration — backend implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task in this session (CLAUDE.md: no subagent-driven execution). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the backend pieces (B1–B11) that let the frontend prototype run on the real API.

**Architecture:** All changes are additive to the existing contexts (`catalog`, `judgment`, `spraying`). Catalog gets richer pesticide and pest data from the static JSON. Spraying gains `pest_id` and soft cancel/restore, and every consumer that decides (judgment input, rotation, duplicate check, `last_spray`) keeps seeing only active rows. Judgment gains a read-only batch preview, an optional harvest-date margin in ②, and returns the chosen drug in its response. `GET /pests` also lists virus pests, responses are gzipped, and identity forwards a field address once Hyebin's item #3 lands.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2 (raw `text()` SQL like `spraying`), psycopg 3, pydantic, pytest, ruff.

**Spec:** `docs/dev/2026-11-02-frontend-integration-design.md` (B1–B11, C1 approved 2026-11-02). The frontend wiring is a separate plan, written after this one lands. Hyebin's items are in `docs/dev/팜가디언_혜빈님_요청_프론트연동.md`.

## Global Constraints

- **Never edit anything under `app/farm`.** The last task checks `git diff origin/test -- app/farm` is empty.
- Additive API changes only. `PesticideBase` and `pesticide_base()` stay exactly as they are (`app/farm/presentation/schemas.py` and `zone_service._last_spray` use them); new data goes in `PesticideDetail` / `pesticide_detail()`.
- Schema changes go in `schema.sql` only (no Alembic). The dev and test databases are changed by hand (`ALTER TABLE`), only after the user says go (Task 6).
- Lint: `ruff check .` (line length 100, rules E/F/I). Tests: `pytest`. DB tests skip without `TEST_DATABASE_URL`; the DB name must end in `_test`.
- Judgment messages must not contain `추천 예측 예상 가능성 위험 확률 안전 문제없`; `tests/test_judgment_wording.py` scans the string literals in `rules.py`.
- Code, identifiers, commit messages in English; comments follow the surrounding code (Korean, sparse).
- Commit trailer: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Commit steps run only with the user's go-ahead.
- Facts pinned by the data (checked 2026-11-02): 1363 drugs; `kind` counts insecticide 763 / fungicide 583 / both 17; every drug has a company, a form, a kind and ≥1 ingredient (rows of one drug never disagree on ingredients); 83 drugs have 2+ companies; 49 of 129 pests have a season row; `virus_vector` has 6 distinct virus ids (5 with a vector, id 64 has none) and none of the 6 has a registered drug; `GET /pests` lists 25 / 43 / 23 pests for 감자 / 배추 / 토마토 before Task 4; drug pools per (crop, pest): 91 pairs, median 18, max 274, 9 above 100; the `dilution` text starts with `N배` in 3665 of 4133 rows and with `-` in 467.
- Hyebin-dependent tasks are 11 (`harvest_at`) and 11b (`address`). Both stop and report instead of editing `app/farm`.
- `docs/dev/팜가디언_PRD_수정_제안.md` is in `.gitignore`: Task 12 edits it on disk, but the commit does not contain it. Say so when reporting.

## Review Focus

1. **A cancelled spray leaking into a decision** (③ count, ④ consecutive window, rotation summary, duplicate check, `last_spray` in `GET /fields`) → tests in Task 8.
2. **Cancel/restore on another zone's or a missing spray, and repeated cancel** → 404 and idempotent 204, tests in Task 6 and 7.
3. **Preview misuse**: missing `pest_id`, a pest of another crop, a foreign zone, `apply_date` after 2100-12-31, and "must store nothing" → Task 9.
4. **Catalog edge data**: drug with several companies, unknown `usage` value, item name without a space, OCR read with every field empty → Tasks 1 and 5.
5. **Harvest margin boundaries**: margin −1 / 0 / 2 / 3, harvest date already past, `phi = 0`, no harvest date, NO_LIMIT and NEEDS_CHECK paths ignoring it → Task 10.
6. **Existing tests that assume "cancel = delete"** (`test_spray_api.py`, `test_spray_service.py`, `test_e2e_scenario.py`) and the three `/pests` count tests that assume "registered only" are rewritten in Tasks 4, 6 and 7, not left to fail.
7. **`at_planting_only` in the judgment response** must agree with `GET /pesticides` for the same drug, crop and pest → Task 2.

## Preflight (before Task 1)

- [ ] `git switch -c feat/frontend-integration-be` (from `test`).
- [ ] Run `pytest -q` and `ruff check .`; note any failures that exist before our change so they are not blamed on it.

---

### Task 1: Pesticide fields from the static data (B2, data layer)

**Files:**
- Create: `app/catalog/domain/pesticide_fields.py`
- Modify: `app/catalog/domain/entities.py` (`Pesticide`), `app/catalog/application/catalog_service.py` (`_drugs()`)
- Test: `tests/test_catalog_pesticide_fields.py`

**Interfaces:**
- Produces: `form_of(item_name: str) -> str | None` (last whitespace token, `None` if there is no space); `kind_of(usage: str) -> str | None` (`살충`→`"insecticide"`, `살균`→`"fungicide"`, `균충`→`"both"`, else `None`).
- Produces: `Pesticide(id, name, item_name, moa, company: str | None = None, form: str | None = None, ingredients: tuple[str, ...] = (), kind: str | None = None)`. Defaults keep every existing constructor call valid.

- [ ] **Step 1: Write the failing tests** in `tests/test_catalog_pesticide_fields.py`:

```python
@pytest.mark.parametrize("item_name,form", [
    ("아미설브롬 입상수화제", "입상수화제"), ("피리달릴.스피네토람 유탁제", "유탁제"), ("공백없음", None)])
def test_form_is_the_last_word_of_the_item_name(item_name, form):
    assert form_of(item_name) == form

@pytest.mark.parametrize("usage,kind", [
    ("살충", "insecticide"), ("살균", "fungicide"), ("균충", "both"), ("제초", None)])
def test_kind_follows_the_usage_column(usage, kind):
    assert kind_of(usage) == kind

def test_every_drug_has_company_form_kind_and_ingredients():
    drugs = svc.all_pesticides()
    assert len(drugs) == 1363
    assert all(d.company and d.form and d.kind and d.ingredients for d in drugs)
    assert Counter(d.kind for d in drugs) == {"insecticide": 763, "fungicide": 583, "both": 17}

def test_company_of_a_multi_company_drug_is_the_first_rows_company():
    rows = [u for u in load("pesticide_use") if (u["product"], u["brand"]) == ("비펜트린 입제", "스퍽")]
    drug = next(d for d in svc.all_pesticides() if (d.item_name, d.name) == ("비펜트린 입제", "스퍽"))
    assert drug.company == min(rows, key=lambda u: u["use_id"])["company"]

def test_ingredients_follow_the_use_ingredient_order():
    # 복합제 하나를 골라 첫 행의 use_ingredient(seq 순) 이름과 같은지 본다
    ...  # builder: pick a drug whose item_name contains "." and compare with load("use_ingredient") / load("ingredient")
```

- [ ] **Step 2: Run** `pytest tests/test_catalog_pesticide_fields.py -v` → FAIL (`pesticide_fields` import error).
- [ ] **Step 3: Implement** the two pure functions in `pesticide_fields.py`; add the four fields to `Pesticide`; in `_drugs()` take `company` and `usage` from each drug's lowest-`use_id` row and `ingredients` from `use_ingredient` ordered by `seq` mapped to `ingredient.name` (a cached `use_id → tuple[str, ...]` helper in `catalog_service`).
- [ ] **Step 4: Run** `pytest tests/test_catalog_pesticide_fields.py tests/test_catalog_pesticide_shape.py tests/test_catalog_service.py -v` → PASS.
- [ ] **Step 5: Commit** `feat(catalog): derive company, form, ingredients and kind for every pesticide`.

### Task 2: `PesticideDetail` on the catalog, OCR, alternatives and judgment responses (B2, B8)

**Files:**
- Modify: `app/catalog/presentation/schemas.py`, `app/catalog/presentation/router.py`, `app/judgment/application/service.py`, `app/judgment/presentation/schemas.py`, `app/judgment/presentation/router.py`
- Test: update `tests/test_catalog_pesticide_shape.py`, `tests/test_catalog_api.py:37`, `tests/test_label_api.py:58`, `tests/test_judgment_api.py:17` (`RESPONSE_KEYS`) and `:20` (`ALT_KEYS`)

**Interfaces:**
- Consumes: `Pesticide` with the new fields (Task 1).
- Produces: `PesticideDetail(PesticideBase)` with `company: str | None`, `form: str | None`, `ingredients: list[str]`, `kind: Literal["insecticide", "fungicide", "both"] | None`; `pesticide_detail(p: Pesticide) -> PesticideDetail`; `PesticideOut(PesticideDetail)` adding `at_planting_only: bool`. `PesticideBase` / `pesticide_base()` unchanged.
- Used by: `GET /pesticides`, `LabelCandidateOut.pesticide`, `JudgeResponse.alternatives` (later Tasks 7 and 9 reuse it).
- Produces (B8): `Assessment` gains `pesticide: Pesticide` (the chosen drug) and `at_planting_only: bool`. The flag is true iff the chosen drug has at least one registration row for the crop (narrowed to `pest_id` when given) and every such row has `parse_status == "stage"`, the same source `list_pesticides` uses. `JudgeResponse` gains `pesticide: PesticideOut`. `RESPONSE_KEYS` = the old keys + `pesticide`.

- [ ] **Step 1: Write the failing tests** (edit the existing shape test, add a converter test):

```python
def test_detail_fields_and_base_stay_separate():
    detail = {"id", "name", "item_name", "moa", "company", "form", "ingredients", "kind"}
    assert set(PesticideDetail.model_fields) == detail
    assert set(PesticideOut.model_fields) == detail | {"at_planting_only"}
    assert set(PesticideBase.model_fields) == {"id", "name", "item_name", "moa"}  # GET /fields

def test_pesticide_detail_converter():
    drug = Pesticide(7, "Brand", "Item", Moa("라3", "FRAC", "24"), "Co", "액제", ("A", "B"), "both")
    assert pesticide_detail(drug).model_dump() == {
        "id": 7, "name": "Brand", "item_name": "Item",
        "moa": {"label_kr": "라3", "system": "FRAC", "code": "24"},
        "company": "Co", "form": "액제", "ingredients": ["A", "B"], "kind": "both"}
```
  Change the three API key-set assertions (`test_catalog_api`, `test_label_api`, `ALT_KEYS`) to the detail key set. Add `"pesticide"` to `RESPONSE_KEYS` and two cases (B8):

```python
def test_response_carries_the_chosen_drug(client, farm):
    body = judge(client, farm, pesticide_id=DRUG.id, pest_id=PEST).json()      # helpers as in this file
    listed = {d["id"]: d for d in pesticide_list(client, farm, crop=CROP, pest_id=PEST)}
    assert body["pesticide"] == listed[DRUG.id]                                  # same shape and flag as GET /pesticides

def test_at_planting_only_agrees_with_the_pesticide_list():
    # for every drug of one pest: assess(...).at_planting_only == the flag from catalog_service.list_pesticides(crop, pest)
    # a drug not registered for the pest, and a judgment without pest_id, give False unless every crop row is `stage`
```
- [ ] **Step 2: Run** `pytest tests/test_catalog_pesticide_shape.py tests/test_catalog_api.py tests/test_label_api.py tests/test_judgment_api.py -v` → FAIL on the new keys.
- [ ] **Step 3: Implement** `PesticideDetail`, `pesticide_detail()`, and switch `_pesticide_out`, the OCR candidate mapping, `JudgeResponse.alternatives` and the judgment router to them. Then add the B8 fields: `assess()` fills `Assessment.pesticide` from `chosen` and `at_planting_only` from `catalog_service.get_registrations`; the router builds `JudgeResponse.pesticide` with the same helper `GET /pesticides` uses (`pesticide_detail()` + the flag).
- [ ] **Step 4: Run** the same files plus `tests/test_zone_summaries.py` (must still pass: `last_spray.pesticide` keeps four keys) → PASS.
- [ ] **Step 5: Commit** `feat(catalog): return PesticideDetail from pesticides, OCR candidates, alternatives and the judgment response`.

### Task 3: Dilution fact on the ① registration check (B3)

**Files:**
- Modify: `app/judgment/domain/rules.py` (`check_registration`, OK branch)
- Test: `tests/test_judge_registration.py` (lines 19 and 97 compare `facts` exactly)

**Interfaces:**
- Produces: the OK result's `facts` become `{"pest_specified": True, "rows": n, "dilution": first.dilut_raw}`; other branches unchanged.

- [ ] **Step 1: Write the failing tests**: update the two exact-dict assertions to include `"dilution": "1000배"`; add

```python
def test_dilution_is_none_when_the_first_row_has_none():
    assert run(registrations=[reg(dilut_raw=None)]).facts["dilution"] is None
```
- [ ] **Step 2: Run** `pytest tests/test_judge_registration.py -v` → FAIL.
- [ ] **Step 3: Implement** the one extra key in the OK branch (the same `first` row already used for `evidence`).
- [ ] **Step 4: Run** `pytest tests/test_judge_registration.py tests/test_judgment_wording.py tests/test_judge_result.py -v` → PASS.
- [ ] **Step 5: Commit** `feat(judgment): expose the dilution on the registration check`.

### Task 4: Pest card fields and virus pests in the pest list (B5, B10)

**Files:**
- Modify: `app/catalog/domain/entities.py`, `app/catalog/application/catalog_service.py` (`get_pest_card`), `app/catalog/presentation/schemas.py`, `app/catalog/presentation/router.py` (`_card_out`)
- Test: `tests/test_catalog_pest_extras.py` (new); update `CARD_KEYS` in `tests/test_catalog_pest_api.py` and the count tests in `tests/test_catalog_pest_lists.py`

**Interfaces:**
- Produces: `PestRef(id: int, name: str)` (frozen dataclass); `PestCard` gains `months: tuple[int, ...] = ()`, `pesticide_count: int = 0`, `is_virus: bool = False`, `carries: tuple[PestRef, ...] = ()`.
- Produces: `PestRefOut(id: int, name: str)` in catalog schemas (Task 7 reuses it); `PestCardOut` gains `months: list[int]`, `pesticide_count: int`, `is_virus: bool`, `carries: list[PestRefOut]`.
- Produces (B10): `_virus_ids()` (cached `frozenset` of `virus_vector.virus_pest_id`), shared by `is_virus` and the list. `list_pests` returns the crop's pests that have a registered drug **or** are in `_virus_ids()`; order and the `q` filter are unchanged; virus cards have `pesticide_count == 0`. Counts become 감자 25 (same), 배추 43 → 45, 토마토 23 → 27.

- [ ] **Step 1: Write the failing tests** in `tests/test_catalog_pest_extras.py`:

```python
def test_months_are_the_chosen_season_rows_months():
    for pest_id, rows in seasons_by_pest().items():          # group load("pest_season") by pest_id
        assert svc.get_pest_card(pest_id).months == tuple(pick_season(rows)["months"])
    assert svc.get_pest_card(a_pest_without_season()).months == ()

def test_is_virus_matches_the_virus_vector_file():
    ids = {p["pest_id"] for p in load("pest") if svc.get_pest_card(p["pest_id"]).is_virus}
    assert ids == {v["virus_pest_id"] for v in load("virus_vector")}

def test_carries_lists_the_viruses_a_vector_carries_sorted_by_name():
    # pick a vector_pest_id from virus_vector; expect PestRef(virus id, virus name) entries sorted by name
    # a virus pest and a pest in no vector row have carries == ()

def test_pesticide_count_equals_the_pool_size():
    for p in load("pest"):
        assert svc.get_pest_card(p["pest_id"]).pesticide_count == len(svc.list_pesticides(p["crop_id"], p["pest_id"]))
```
  Add the four keys to `CARD_KEYS`; one API assertion that a virus card (pick one with a vector; id 64 has none) has `is_virus is True` and a non-empty `vectors`. Add the B10 cases and update the tests that assume "registered only":

```python
def test_virus_pests_are_listed_although_no_drug_is_registered_for_them():
    virus_ids = {v["virus_pest_id"] for v in load("virus_vector")}
    for crop_id in (1, 2, 3):
        mine = {p["pest_id"] for p in pests_of(crop_id)} & virus_ids
        assert mine <= {c.id for c in svc.list_pests(crop_id)}

def test_q_finds_a_virus_by_name():
    assert "모자이크병" in [c.name for c in svc.list_pests(2, "모자이크")]
```

  In `tests/test_catalog_pest_lists.py`: `test_registered_pest_counts` becomes `[(1, 25), (2, 45), (3, 27)]`; `test_listed_pests_are_exactly_the_registered_pests_of_the_crop` expects registered ∪ virus ids (rename it); `test_candidates_are_not_limited_to_registered_pests` expects `len(listed) == 27` (`candidates - listed` stays non-empty). Also fix any `/pests` count assertion in `tests/test_catalog_pest_api.py`.
- [ ] **Step 2: Run** `pytest tests/test_catalog_pest_extras.py tests/test_catalog_pest_api.py -v` → FAIL.
- [ ] **Step 3: Implement** in `get_pest_card`: `months` from `pick_season(...)`; `is_virus` from a cached set of `virus_vector.virus_pest_id`; `carries` from `virus_vector` grouped by `vector_pest_id` (skip null vectors, sorted by name); `pesticide_count` from a cached `{(crop_id, pest_id): n}` built once from `_drugs()` rows (distinct drugs), not a scan per card. Change the `list_pests` condition to `pest_id in _registered_pest_ids() or pest_id in _virus_ids()`.
- [ ] **Step 4: Run** `pytest tests/test_catalog_pest_extras.py tests/test_catalog_pest_api.py tests/test_catalog_pest_cards.py tests/test_catalog_pest_lists.py -v` → PASS.
- [ ] **Step 5: Commit** `feat(catalog): add months, drug count, virus flag and carried viruses to the pest card, and list virus pests`.

### Task 5: OCR `matched` (B6)

**Files:**
- Modify: `app/catalog/domain/entities.py` (`LabelCandidate`), `app/catalog/domain/label_match.py`, `app/catalog/application/label_service.py`, `app/catalog/presentation/schemas.py` (`LabelCandidateOut`), `app/catalog/presentation/router.py`
- Test: `tests/test_label_match.py`, `tests/test_label_api.py`

**Interfaces:**
- Consumes: `Pesticide.company` (Task 1); `PesticideDetail` in `LabelCandidateOut` (Task 2).
- Produces: `LabelCandidate(pesticide, score, matched: tuple[str, ...] = ())`; `rank_candidates(brand, product, drugs, *, company: str | None = None, limit=..., cutoff=...)`; `MATCH_THRESHOLD = 0.9`; `LabelCandidateOut.matched: list[str]`, order always `brand, product, company`.
- Rule: `brand` matches when the normalized read brand vs `drug.name` has ratio ≥ 0.9; `product` vs `item_name` the same; `company` matches when the normalized read company and `drug.company` have ratio ≥ 0.9 **or one contains the other** (so 「경농」 matches 「(주)경농」; my call). A field that was not read never matches. `score` and ranking are unchanged (company is not part of the score).

- [ ] **Step 1: Write the failing tests**:

```python
TARGET = Pesticide(1, "카브리오", "피라클로스트로빈 유제", None, "(주)경농")

def test_matched_lists_the_agreeing_fields_in_a_fixed_order():
    r = rank_candidates("카브리오", "피라클로스트로빈 유제", [TARGET], company="(주)경농")
    assert r[0].matched == ("brand", "product", "company")

def test_company_matches_by_containment_and_unread_fields_never_match():
    assert rank_candidates("카브리오", None, [TARGET], company="경농")[0].matched == ("brand", "company")
    assert rank_candidates("카브리오", None, [TARGET])[0].matched == ("brand",)

def test_a_different_brand_with_the_same_product_matches_only_the_product():
    r = rank_candidates("카브리", "피라클로스트로빈 유제", [TARGET])   # brand ratio < 0.9
    assert r[0].matched == ("product",)

def test_company_does_not_change_the_score():
    a = rank_candidates("카브리오", "피라클로스트로빈 유제", [TARGET])[0].score
    b = rank_candidates("카브리오", "피라클로스트로빈 유제", [TARGET], company="없는회사")[0].score
    assert a == b

def test_nothing_read_gives_no_candidates():
    assert rank_candidates(None, None, [TARGET], company="(주)경농") == []
```
  In `test_label_api.py` add `matched` to the candidate key set and assert `first["matched"]` for a fake read with brand, product and company all equal to the drug's.
- [ ] **Step 2: Run** `pytest tests/test_label_match.py tests/test_label_api.py -v` → FAIL.
- [ ] **Step 3: Implement**; `label_service.scan_label` passes `company=read.company`. Reuse `_ratio` and `normalize`.
- [ ] **Step 4: Run** `pytest tests/test_label_match.py tests/test_label_service.py tests/test_label_api.py -v` → PASS (existing score assertions untouched).
- [ ] **Step 5: Commit** `feat(catalog): return which label fields matched each OCR candidate`.

### Task 6: Spray `pest_id` and soft cancel — schema, repository, service (B4)

**Files:**
- Modify: `schema.sql` (`spray_log`), `app/spraying/domain/entities.py`, `app/spraying/infrastructure/repository.py`, `app/spraying/application/spray_service.py`
- Test: `tests/test_spray_cancel.py` (new); `tests/test_schema_sql.py` (add a columns check); rewrite the existing cancel tests listed in Step 1

**Interfaces:**
- Produces: `Spray(id, pesticide_id, sprayed_on, source, pest_id: int | None = None, cancelled: bool = False)`; `SprayView(spray, pesticide, pest: PestCard | None = None)`.
- Produces (repository): `insert(..., pest_id: int | None = None)`; `page(db, zone_id, limit, offset, include_cancelled=False)`; `cancel(db, zone_id, spray_id) -> bool` (sets `cancelled_at` once, keeps the first time; `False` only when the row is not in that zone); `restore(db, zone_id, spray_id) -> Spray | None`. `find_duplicate` and `all_for_zone` exclude cancelled rows; `find_by_request_id` does not.
- Produces (service): `record_spray(..., pest_id: int | None = None)` (unknown pest → 422 `loc ["body","pest_id"]`, existence only, uses `catalog_service.get_pest_card`); `list_sprays(db, zone_id, limit=20, offset=0, *, include_cancelled=False)`; `cancel_spray(db, zone_id, spray_id) -> None` (404 when absent, repeat is fine); `restore_spray(db, zone_id, spray_id) -> SprayView` (404 when absent).

- [ ] **Step 1: Write the failing tests** in `tests/test_spray_cancel.py` (helpers `record`, `zones`, `total` as in `test_spray_service.py`):

```python
def test_cancelled_spray_leaves_history_duplicates_and_the_default_listing(db, zones):
    view, _ = record(db, zones[0])
    svc.cancel_spray(db, zones[0], view.spray.id)
    assert svc.history(db, zones[0]) == [] and total(db, zones[0]) == 0
    record(db, zones[0])                                  # same zone, drug, day: no DuplicateSpray

def test_include_cancelled_marks_the_row(db, zones):
    view, _ = record(db, zones[0]); svc.cancel_spray(db, zones[0], view.spray.id)
    count, rows = svc.list_sprays(db, zones[0], include_cancelled=True)
    assert (count, [r.spray.cancelled for r in rows]) == (1, [True])

def test_cancel_twice_is_fine_and_restore_brings_the_row_back(db, zones):
    view, _ = record(db, zones[0]); sid = view.spray.id
    svc.cancel_spray(db, zones[0], sid); svc.cancel_spray(db, zones[0], sid)
    assert svc.restore_spray(db, zones[0], sid).spray.cancelled is False
    assert total(db, zones[0]) == 1

def test_cancel_and_restore_are_scoped_to_the_zone(db, zones):
    view, _ = record(db, zones[0])
    for call in (svc.cancel_spray, svc.restore_spray):
        with pytest.raises(AppError) as info:
            call(db, zones[1], view.spray.id)
        assert (info.value.status, info.value.code) == (404, "NOT_FOUND")

def test_pest_id_is_stored_and_an_unknown_pest_is_422(db, zones):
    pest = pests_with_drugs(1)[0]
    view, _ = record(db, zones[0], pest_id=pest)
    assert view.spray.pest_id == pest and view.pest.id == pest
    with pytest.raises(AppError) as info:
        record(db, zones[0], pest_id=999999)
    assert info.value.details["errors"][0]["loc"] == ["body", "pest_id"]
```
  In `test_schema_sql.py` add a check that `spray_log` has `pest_id` and `cancelled_at` columns.

  Rewrite the existing tests that assume cancel = delete (none calls `repository.delete` directly; the rename only touches `spray_service`):
  - `tests/test_spray_service.py::test_cancel_removes_the_record` still passes (the `total` helper uses the default listing); rename it to say the cancelled row leaves the default listing.
  - `tests/test_spray_service.py::test_cancel_twice_or_unknown_is_404` (lines 231-238): a repeated cancel no longer raises. Keep only the unknown id (999999) → 404; the repeat case is covered by `test_cancel_twice_is_fine_and_restore_brings_the_row_back`.
  - `tests/test_e2e_scenario.py` (lines 71-74): after the cancel, `GET /sprays` still returns the cancelled row. Count only items with `cancelled == False` (2 → 1 → 2) instead of `total`.
- [ ] **Step 2: Edit `schema.sql`**: add `pest_id int` (comment: static pest id, no FK) and `cancelled_at timestamptz` to `spray_log`.
- [ ] **Step 3: Ask the user for a go-ahead, then change the databases.** Against the test database (`TEST_DATABASE_URL` in `.env`, name ends in `_test`) and the dev database run (Windows: `set PGCLIENTENCODING=UTF8` first):
  `ALTER TABLE spray_log ADD COLUMN pest_id int, ADD COLUMN cancelled_at timestamptz;`
  Tell the user to share the same statement with teammates. Do not run it without the go-ahead.
- [ ] **Step 4: Run** `pytest tests/test_spray_cancel.py tests/test_schema_sql.py -v` → FAIL (code not written).
- [ ] **Step 5: Implement** the interfaces above. `SELECT` lists add `pest_id, cancelled_at`; `_spray(row)` sets `cancelled=row.cancelled_at is not None`; `_view` fills `pest` from `catalog_service.get_pest_card`; rename the repository's `delete` to `cancel` and update its callers and tests.
- [ ] **Step 6: Run** `pytest tests/test_spray_cancel.py tests/test_spray_service.py tests/test_spray_history.py tests/test_schema_sql.py -v` → PASS.
- [ ] **Step 7: Commit** `feat(spraying): store pest_id and cancel sprays softly with restore`.

### Task 7: Spray API — pest, cancelled flag, restore route (B4)

**Files:**
- Modify: `app/spraying/presentation/schemas.py`, `app/spraying/presentation/router.py`
- Test: `tests/test_spray_api.py`

**Interfaces:**
- Consumes: Task 6 service; `PesticideDetail`/`pesticide_detail` (Task 2); `PestRefOut` (Task 4).
- Produces: `SprayIn.pest_id: int | None = None`; `SprayOut(id, pesticide: PesticideDetail, pest: PestRefOut | None, sprayed_on, source, cancelled: bool)`; `GET /zones/{id}/sprays` calls `list_sprays(..., include_cancelled=True)`; `POST /zones/{zone_id}/sprays/{spray_id}/restore` → 200 `SprayOut`; `DELETE` stays 204.

- [ ] **Step 1: Write the failing tests**: set `SPRAY_KEYS = {"id","pesticide","pest","sprayed_on","source","cancelled"}` and `PESTICIDE_KEYS` to the detail key set; add

```python
def test_delete_keeps_the_row_marked_cancelled_and_restore_undoes_it(client, farm):
    uid, zone = farm
    sid = save(client, uid, zone).json()["id"]
    assert client.delete(f"/zones/{zone}/sprays/{sid}", headers=auth(uid)).status_code == 204
    page = listing(client, uid, zone).json()
    assert (page["total"], page["items"][0]["cancelled"]) == (1, True)
    r = client.post(f"/zones/{zone}/sprays/{sid}/restore", headers=auth(uid))
    assert (r.status_code, r.json()["cancelled"]) == (200, False)

def test_post_with_pest_id_echoes_the_pest(client, farm): ...        # body["pest"] == {"id": pest, "name": <catalog name>}
def test_pest_is_null_when_not_sent(client, farm): ...
def test_restore_requires_authentication_and_404s_for_foreign_or_missing(client, ...): ...
```
  Add the restore path to `test_requires_authentication`'s parametrization and to the foreign/unknown-zone 404 test. Replace `test_cancel_returns_204_and_removes_the_spray` (lines 216-224), which asserts `total == 0` after the cancel and a 404 on the second `DELETE`: both now differ (the row stays with `cancelled: true`, and the second `DELETE` is 204). The new test above covers the 204 and the `cancelled` flag; keep a second-`DELETE` → 204 assertion in it.
- [ ] **Step 2: Run** `pytest tests/test_spray_api.py -v` → FAIL.
- [ ] **Step 3: Implement** schemas, `_spray_out`, the `include_cancelled=True` listing and the restore route.
- [ ] **Step 4: Run** `pytest tests/test_spray_api.py tests/test_zone_summaries.py tests/test_fields_api.py -v` → PASS.
- [ ] **Step 5: Commit** `feat(spraying): expose pest, cancelled flag and restore on the spray API`.

### Task 8: Cancelled sprays never decide (B4 regression)

**Files:**
- Test: `tests/test_spray_cancel_effects.py` (new). Code changes only if a test fails.

**Interfaces:**
- Consumes: Tasks 6–7, `tests/judgment_scenarios.py` (`counting_selection`, `PLANTED`, `pool`).

- [ ] **Step 1: Write the tests** (API level; helpers `auth`, `farm` as in `test_judgment_api.py`; confirm the zone with `UPDATE zone SET planted_at = :PLANTED, history_confirmed = true`):

```python
def test_cancelled_spray_is_not_counted_by_the_count_check(client, db, farm):
    # spray counting_selection's drug once, judge: ③ facts["used"] == 1
    # cancel it: used == 0; restore it: used == 1

def test_cancelled_spray_is_not_in_the_rotation_summary(client, db, farm):
    # GET /zones/{id}: rotation["total"] drops by one after cancel and returns after restore

def test_last_spray_on_the_fields_list_skips_cancelled_rows(client, db, farm):
    # two sprays on different days: cancel the newer one: GET /fields zone summary last_spray is the older;
    # cancel both: last_spray is None
```
- [ ] **Step 2: Run** `pytest tests/test_spray_cancel_effects.py -v` → PASS (default exclusion from Task 6). If one fails, fix the consumer in `spraying`/`judgment` (not `app/farm`).
- [ ] **Step 3: Commit** `test(spraying): cancelled sprays do not count, rotate or show as last spray`.

### Task 9: Read-only batch preview (B1)

**Files:**
- Modify: `app/judgment/application/service.py`, `app/judgment/presentation/schemas.py`, `app/judgment/presentation/router.py`, `app/main.py` (gzip, B9)
- Test: `tests/test_judgment_preview.py` (new); keep `tests/test_judgment_assess.py` green

**Interfaces:**
- Consumes: `PesticideDetail`/`pesticide_detail` (Task 2).
- Produces (service): module-level `judge_drug(drug: Pesticide, *, crop_id, planted_at, history_confirmed, records: list[SprayRecord], pest_id: int | None, today: date, asof: date) -> JudgeResult` (the body of `assess`'s `judged()` closure, which now calls it); `_day(apply_date: date | None, today: date) -> date` (the `MAX_APPLY_DATE` check, shared with `run_judgment`); `PreviewItem(entry: PesticideEntry, result: JudgeResult)`; `preview(db, zone_id, *, pest_id: int, apply_date: date | None, today: date) -> list[PreviewItem]`.
- Produces (API): `GET /zones/{zone_id}/judgments/preview?pest_id=<int>&apply_date=<date>` → `[PreviewItemOut(pesticide: PesticideDetail, at_planting_only: bool, result: JudgeResult)]`, ordered as `list_pesticides(crop_id, pest_id)`. Stores nothing.

- [ ] **Step 1: Write the failing tests** (`PEST = pests_with_drugs(1)[0]`, `farm` fixture as in `test_judgment_api.py`):

```python
def preview(client, uid, zone, **params):
    return client.get(f"/zones/{zone}/judgments/preview", params=params, headers=auth(uid))

def test_requires_authentication(client):
    assert client.get("/zones/1/judgments/preview", params={"pest_id": 1}).status_code == 401

def test_foreign_and_unknown_zones_are_404(client, make_user, make_field, make_zone, farm): ...

def test_missing_pest_id_is_422(client, farm):
    r = preview(client, *farm)
    assert (r.status_code, r.json()["error"]["details"]["errors"][0]["loc"]) == (422, ["query", "pest_id"])

@pytest.mark.parametrize("pest_id", [999999, pests_with_drugs(2)[0]], ids=["unknown", "other-crop"])
def test_unknown_pest_or_another_crops_pest_is_404(client, farm, pest_id): ...

def test_apply_date_after_2100_is_422(client, farm): ...

def test_items_follow_the_pool_order_and_carry_a_full_result(client, farm):
    body = preview(client, *farm, pest_id=PEST).json()
    assert [i["pesticide"]["id"] for i in body] == [d.id for d in pool(1, PEST)]
    assert all(set(i) == {"pesticide", "at_planting_only", "result"} for i in body)
    assert all(set(i["result"]) == RESULT_KEYS for i in body)

def test_each_result_equals_the_one_a_judgment_would_give(client, farm):
    # for the first three drugs: POST /judgments with the same pest_id; body["result"] == item["result"]

def test_preview_stores_nothing(client, db, farm):
    # count rows in judgment before and after: unchanged
```
  Add one case for B9: a preview request sent with `Accept-Encoding: gzip` answers with `content-encoding: gzip`, and a tiny response (`GET /health`) does not.
- [ ] **Step 2: Run** `pytest tests/test_judgment_preview.py -v` → FAIL (404 route).
- [ ] **Step 3: Implement** the refactor first (`judge_drug`, `_day`; `assess` and `run_judgment` call them), then `preview()` (one `zone_reader.get_zone_context`, one `spray_service.history`, `catalog_service.list_pesticides` for the pool, `judge_drug` per drug), then schema and route (`get_owned_zone` dependency like the POST). Last, add `app.add_middleware(GZipMiddleware, minimum_size=1000)` in `app/main.py` (B9; the biggest pool is 274 drugs, each with a full `JudgeResult`).
- [ ] **Step 4: Run** `pytest tests/test_judgment_preview.py tests/test_judgment_assess.py tests/test_judgment_api.py tests/test_judgment_sweep.py -v` → PASS.
- [ ] **Step 5: Commit** `feat(judgment): add a read-only batch preview for a zone and pest, and gzip responses`.

### Task 10: ② harvest-date margin, domain and plumbing (B7 / C1, approved 2026-11-02)

**Files:**
- Modify: `app/judgment/domain/schemas.py` (`JudgeInput`), `app/judgment/domain/rules.py` (`check_timing`), `app/judgment/application/service.py` (`judge_drug`, `assess`, `preview`, `run_judgment` accept and pass `harvest_at`)
- Test: `tests/test_judge_timing.py`

**Interfaces:**
- Produces: `JudgeInput.harvest_at: date | None = None`; `assess(..., harvest_at: date | None = None)`, `judge_drug(..., harvest_at: date | None = None)`.
- Rule (only on the path that has a readable `phi`; NO_LIMIT, AT_PLANTING and unreadable paths ignore `harvest_at` and add no keys): `margin = (harvest_at − today).days − phi`. `margin < 0` → `BLOCKED`; `0 ≤ margin ≤ 2` → `CAUTION`; otherwise `OK` with the existing message. Keys `harvest_at` (ISO string) and `margin_days` (int) are added to `facts` **only when `harvest_at` is given**, so existing exact-dict tests stay valid.
- Messages (exact; `d` = `format_date_kr(harvest_at, today)`):
  - BLOCKED, harvest date today or later: `수확 예정일({d})까지 {left}일 남아 수확 {phi}일 전까지 사용하는 기준을 지킬 수 없습니다` (`left = (harvest_at − today).days`)
  - BLOCKED, harvest date before today: `수확 예정일({d})이 지났습니다`
  - CAUTION: `수확 예정일({d})까지 여유가 {margin}일입니다 (수확 {phi}일 전까지 사용)`

- [ ] **Step 1: Write the failing tests** (today = `TODAY` 2026-10-04, base `phi = 7`; use `timing(harvest_at=...)`):

```python
@pytest.mark.parametrize("harvest_at,status,margin", [
    (date(2026, 10, 10), BLOCKED, -1), (date(2026, 10, 11), CAUTION, 0),
    (date(2026, 10, 13), CAUTION, 2), (date(2026, 10, 14), OK, 3)])
def test_margin_boundaries(harvest_at, status, margin):
    r = timing(harvest_at=harvest_at)
    assert (r.status, r.facts["margin_days"], r.facts["harvest_at"]) == (status, margin, harvest_at.isoformat())

def test_a_harvest_date_in_the_past_is_blocked_with_its_own_message():
    assert timing(harvest_at=date(2026, 10, 1)).message == "수확 예정일(10월 1일)이 지났습니다"

def test_phi_zero_on_the_harvest_day_is_caution():            # registrations=[reg(phi_days=0, ...)], harvest_at=TODAY
def test_no_harvest_date_changes_nothing():                    # facts == facts(7, "2026-10-11", 1, "발생 초부터 경엽처리")
def test_no_limit_and_needs_check_paths_ignore_the_harvest_date():   # no "margin_days" key, status as before
```
- [ ] **Step 2: Run** `pytest tests/test_judge_timing.py -v` → FAIL.
- [ ] **Step 3: Implement** the rule in `check_timing` and the optional `harvest_at` plumbing in the service functions (default `None`; `run_judgment` and `preview` do **not** pass it yet).
- [ ] **Step 4: Run** `pytest tests/test_judge_timing.py tests/test_judgment_wording.py tests/test_judge_verdict.py tests/test_judgment_assess.py -v` and `ruff check .` → PASS.
- [ ] **Step 5: Commit** `feat(judgment): judge the harvest-date margin when the zone has a harvest date`.

### Task 11: Wire the zone's `harvest_at` into judgments — BLOCKED until Hyebin's item #1 lands

**Files:**
- Modify: `app/judgment/application/service.py` (`run_judgment`, `preview`)
- Test: `tests/test_judgment_api.py` (one case), `tests/test_judgment_preview.py` (one case)

**Do not start** until `zone.harvest_at` exists in `schema.sql` and `ZoneContext.harvest_at` exists in `app/farm/application/zone_reader.py` (check with `grep -n harvest_at schema.sql app/farm/application/zone_reader.py`). If it is not there, stop and tell the user; do not edit `app/farm`.

- [ ] **Step 1: Write the failing tests**: set `harvest_at` on a confirmed zone by SQL; `POST /judgments` and `GET .../preview` both return ② with `facts["margin_days"]` and the status from Task 10 for a drug whose strict `phi` is known (choose via `counting_selection`).
- [ ] **Step 2: Run** the two tests → FAIL.
- [ ] **Step 3: Pass `harvest_at=zone.harvest_at`** into `assess`/`judge_drug` in `run_judgment` and `preview`.
- [ ] **Step 4: Run** `pytest tests/test_judgment_api.py tests/test_judgment_preview.py -v` → PASS.
- [ ] **Step 5: Commit** `feat(judgment): use the zone's harvest date in the timing check`.

### Task 11b: Field address through signup — BLOCKED until Hyebin's item #3 lands (B11)

**Files:**
- Modify: `app/identity/presentation/schemas.py` (`SignupIn`), `app/identity/presentation/router.py`, `app/identity/application/service.py` (`signup`)
- Test: `tests/test_identity_signup.py`, `tests/test_identity_api.py`

**Do not start** until `schema.sql` has `field.address`, `FieldOut` has `address` and `field_service.create_field` accepts an `address` argument (check with `grep -n address schema.sql app/farm/presentation/schemas.py app/farm/application/field_service.py`). If they are not there, stop and tell the user; do not edit `app/farm`. If Hyebin declines item #3, drop this task (the frontend keeps the address in the browser).

**Interfaces:**
- Produces: `SignupIn.field_address: str | None = None` (stripped, 1–200 characters when given, like `field_name`; a blank or longer value is 422 `loc ["body","field_address"]`); `signup(db, username, password, field_name, farmmap_ids, address=None)` forwards it to `field_service.create_field`; the response `field.address` echoes it.

- [ ] **Step 1: Write the failing tests**: signup with `field_address` → 201 and `field.address` equals it; without it → `field.address is None`; a blank value and a 201-character value → 422 on `["body","field_address"]`; a failed signup (unknown farmmap id) still leaves no user.
- [ ] **Step 2: Run** `pytest tests/test_identity_signup.py tests/test_identity_api.py -v` → FAIL.
- [ ] **Step 3: Implement** the schema field, the router pass-through and the service argument.
- [ ] **Step 4: Run** the same files plus `tests/test_fields_api.py` and `ruff check .` → PASS.
- [ ] **Step 5: Commit** `feat(identity): accept the first field's address at signup`.

### Task 12: Documents and final verification

**Files:**
- Modify: `docs/dev/팜가디언_API_명세.md`, `docs/dev/팜가디언_판정_규칙.md`, `docs/dev/팜가디언_PRD_수정_제안.md` (git-ignored: edit it, it is not part of the commit), `docs/dev/팜가디언_아키텍처.md`, `docs/dev/2026-11-02-frontend-integration-design.md`; check `docs/dev/api_playground.html` for the endpoints it lists.

- [ ] **Step 1: 명세**: endpoint count 28 → 30 (counting the unbuilt weather one) in §0/title text; `Pesticide` → detail fields and `PestCard` → four new fields in §2; new §7 section for `GET /zones/{id}/judgments/preview`; §7 `registration` facts add `dilution`; §7 `timing` facts add `harvest_at`/`margin_days` (only when set); §8 spray: `pest_id`, `pest`, `cancelled`, soft cancel wording, the `restore` route, `GET` includes cancelled rows; OCR candidate `matched`; §2 `ZoneSummary.last_spray` keeps the old four-key `Pesticide` shape while `Spray` now has the detail fields, `pest` and `cancelled`; §6 `GET /pests` also returns virus pests (B10); §7 `JudgeResponse.pesticide` (B8); responses are gzipped (B9); `address` on `Field`, `POST /fields` and signup `field_address` if Task 11b lands. Mark new choices `【결정】`.
- [ ] **Step 2: 판정 규칙**: §1 row ② and §4 ② describe the margin rule and its messages; §4 ① facts add `dilution`; §9 add the boundary cases from Task 10.
- [ ] **Step 3: PRD 수정 제안**: add the ② change (harvest date input, BLOCKED/CAUTION by margin, unchanged when the date is empty) with the reason (a harvest inside the pre-harvest interval is a shipping ban). The file is git-ignored; tell the user it was edited on disk only.
- [ ] **Step 4: 아키텍처**: §2 ② 시기 row (margin when `harvest_at` is set) and 살포 기록 row (취소 = 소프트 취소, 복구); §5 `spray_log` columns (and `field.address` if Task 11b lands); §7 `GET /pests` sentence (registered pests **or** virus pests), API table rows for preview and restore; §8 브이월드 지오코더 「미정: 주소를 어느 응답에 넣을지」 → closed by `Field.address`.
- [ ] **Step 5: Design doc**: Status → approved (2026-11-02) with C1 approved; note which plan tasks implement each B-item.
- [ ] **Step 6: Final verification** (superpowers:verification-before-completion): run `pytest -q`, `ruff check .`, and `git diff origin/test -- app/farm` (must print nothing). Report the real output; any failure that also failed in Preflight is reported as pre-existing.
- [ ] **Step 7: Commit** `docs: record the frontend-integration API changes` (without `팜가디언_PRD_수정_제안.md`, which is git-ignored).
