# Pest Endpoints Implementation Plan (BE-36)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (project CLAUDE.md: no subagent-driven execution). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `GET /crops/{id}/symptom-parts`, `GET /pests/candidates` and `GET /pests`, returning `PestCard`s built from the static catalog data, in the shape of the API spec.

**Architecture:** pure card rules in `app/catalog/domain/pest_rules.py`; `PestCard`/`PestVector` entities in `domain/entities.py`; pest functions next to the pesticide ones in `application/catalog_service.py`; three routes and schemas in `presentation/`. All routes are behind `current_user` (the router already is).

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, pytest (`client`, `make_user` fixtures for the API tests).

**Spec:** `docs/dev/2026-10-29-catalog-pests-design.md` (approved in chat 2026-10-29); frame = `docs/dev/팜가디언_API_명세.md` (never edited).

## Global Constraints

- `팜가디언_API_명세.md` is the frame and **must not change**: no commit of this plan touches it.
- A card serializes to exactly `{id, name, kind, photo_url, photo_source, description, occurrence, occurrence_source, vectors}` with `vectors` items `{id, name, guide, source}`; `kind` is `"병"`, `"해충"` or null; absent values are JSON `null`, `vectors` is `[]` when empty.
- `kind`: `disease` → 병, `insect` → 해충. `description` = `pest.symptom` (null when empty).
- Photo: the pest's `is_main` photo (lowest `photo_id` if several), else its photo with the lowest `photo_id`; `photo_url` = its `url`, `photo_source` = `pest.photo_crop`; no photo → both null.
- Occurrence: use the pest's `ncpms` season row, else its `pdf` row, else none. `occurrence_source`: `ncpms` → 「NCPMS 설명」, `pdf` → 「PDF 경보」. `occurrence` = months text, plus ` — ` and the basis when there is one. Months text: unique, sorted, runs of two or more consecutive months as `a~b`, joined with `, `, ending in `월` (`[4,5,6,7]` → `4~7월`, `[6,8,9]` → `6, 8~9월`, `[6]` → `6월`). Basis: `ncpms` → its `evidence`; `pdf` → the non-empty ones of `region`, `culti`, `grade` joined with ` · `.
- Vectors: one per `virus_vector.json` row of the virus with a vector pest (`id` = vector pest id, `name` = its name, `guide` = `guide_text`, `source` = `evidence`), ordered by name.
- Symptom parts of a crop: its pests' distinct `parts` values in the fixed order 덩이, 뿌리, 잎, 줄기, 벌레, 열매. Candidates: pests of the crop whose `parts` contain `part`, registered or not. `GET /pests`: pests of the crop with at least one `pesticide_use` row; `q` trimmed, blank = no filter, else case-insensitive substring of the name. Order: name ascending.
- Errors in the common format: unknown crop → 404 `NOT_FOUND`; a `part` not in the crop's symptom-part list → 422 `VALIDATION_ERROR` with `details.errors = [{loc: ["query", "part"], msg, type}]` (the value is not echoed); missing/non-integer query values → 422; no `X-User-Id` → 401.
- No database access in the service; no change to `schema.sql`.
- Code and identifiers in English, short Korean comments as in `app/core`; ruff line length 100 (Korean characters count double, wrap long strings); tests flat in `tests/`; commit messages in English; do not push.

## Review Focus

- The representative-photo rule is tested on synthetic data, because on the real data `is_main` always equals the lowest `photo_id`. (Task 1)
- Occurrence: the `ncpms` row wins over `pdf` for the two pests that have both; month runs, unsorted and duplicate months format correctly. (Tasks 1, 2)
- Candidates are not limited to registered pests (토마토: 43 candidates vs 23 listed pests), and a pest with several parts appears under each. (Task 3)
- A `part` valid in general but absent for the crop is a 422, not an empty list. (Tasks 3, 4)
- Cards are complete and consistent over all 129 pests: 102 with photos, 49 with occurrence, 5 with vectors. (Task 2)

---

### Task 0: Commit the design and this plan

- [ ] **Step 1:** `git add docs/dev/2026-10-29-catalog-pests-design.md docs/dev/2026-10-29-catalog-pests-plan.md` / `git commit -m "Add catalog pests design and plan"`

### Task 1: Pure card rules

**Files:**
- Create: `app/catalog/domain/pest_rules.py`
- Test: `tests/test_catalog_pest_rules.py`

**Interfaces:**
- Produces in `pest_rules.py`: `format_months(months: Sequence[int]) -> str`; `pick_season(rows: Sequence[Mapping]) -> Mapping | None` (the `ncpms` row, else the `pdf` row, else None; rows are `pest_season.json` dicts with `source`); `occurrence_text(row: Mapping) -> str`; `representative_photo(photos: Sequence[Mapping]) -> Mapping | None` (rows are `pest_photo.json` dicts with `photo_id`, `is_main`); `OCCURRENCE_SOURCES = {"ncpms": "NCPMS 설명", "pdf": "PDF 경보"}`. No imports from other layers.

- [ ] **Step 1: Write the failing tests** in `tests/test_catalog_pest_rules.py`
```python
import pytest

from app.catalog.domain.pest_rules import (
    OCCURRENCE_SOURCES,
    format_months,
    occurrence_text,
    pick_season,
    representative_photo,
)


@pytest.mark.parametrize(
    "months,text",
    [
        ([4, 5, 6, 7], "4~7월"),
        ([6, 8, 9], "6, 8~9월"),
        ([6], "6월"),
        ([6, 7], "6~7월"),
        ([9, 6, 8], "6, 8~9월"),
        ([1, 2, 3, 12], "1~3, 12월"),
        ([6, 6, 7], "6~7월"),
        ([10, 11, 12], "10~12월"),
    ],
)
def test_format_months(months, text):
    assert format_months(months) == text


def season(source, months, **kw):
    base = {"source": source, "months": months, "region": None, "culti": None,
            "grade": None, "evidence": None}
    return {**base, **kw}


def test_occurrence_text_ncpms_uses_the_evidence_sentence():
    row = season("ncpms", [4, 5, 6, 7], evidence="유충은 4월경에 부화한다")

    assert occurrence_text(row) == "4~7월 — 유충은 4월경에 부화한다"


def test_occurrence_text_ncpms_without_evidence_is_months_only():
    assert occurrence_text(season("ncpms", [4, 5])) == "4~5월"


def test_occurrence_text_pdf_joins_region_culti_and_grade():
    row = season("pdf", [6, 7], region="대관령", culti="고랭지, 씨감자", grade="예보")

    assert occurrence_text(row) == "6~7월 — 대관령 · 고랭지, 씨감자 · 예보"


def test_occurrence_text_pdf_skips_missing_parts():
    assert occurrence_text(season("pdf", [8, 9], grade="주의보")) == "8~9월 — 주의보"
    assert occurrence_text(season("pdf", [8, 9])) == "8~9월"


def test_occurrence_sources():
    assert OCCURRENCE_SOURCES == {"ncpms": "NCPMS 설명", "pdf": "PDF 경보"}


def test_pick_season_prefers_ncpms_then_pdf_then_none():
    ncpms, pdf = season("ncpms", [6]), season("pdf", [7])

    assert pick_season([pdf, ncpms]) is ncpms
    assert pick_season([pdf]) is pdf
    assert pick_season([ncpms]) is ncpms
    assert pick_season([]) is None


def photo(photo_id, is_main=False):
    return {"photo_id": photo_id, "is_main": is_main, "url": f"u{photo_id}"}


def test_representative_photo_falls_back_to_the_lowest_photo_id():
    assert representative_photo([photo(3), photo(1), photo(2)])["photo_id"] == 1


def test_representative_photo_prefers_the_main_one_even_when_not_first():
    assert representative_photo([photo(1), photo(5, True), photo(2)])["photo_id"] == 5


def test_representative_photo_with_several_mains_takes_the_lowest_id():
    assert representative_photo([photo(7, True), photo(4, True), photo(1)])["photo_id"] == 4


def test_representative_photo_single_and_empty():
    assert representative_photo([photo(9)])["photo_id"] == 9
    assert representative_photo([]) is None
```
- [ ] **Step 2: Run** `.venv\Scripts\python -m pytest tests\test_catalog_pest_rules.py -q` — Expected: collection ERROR `No module named 'app.catalog.domain.pest_rules'`.
- [ ] **Step 3: Implement** the four functions and the constant per the interface block and constraints.
- [ ] **Step 4: Run** the step 2 command — Expected: `18 passed` (8 month formats, 4 occurrence texts, 1 sources, 1 season pick, 4 photo rules). Full suite and `ruff check .` clean.
- [ ] **Step 5: Commit** `git add app/catalog/domain/pest_rules.py tests/test_catalog_pest_rules.py` / `git commit -m "Add pest card rules"`

### Task 2: Pest cards

**Files:**
- Modify: `app/catalog/domain/entities.py`, `app/catalog/application/catalog_service.py`
- Test: `tests/test_catalog_pest_cards.py`

**Interfaces:**
- Consumes: `pest_rules` (Task 1), `static_data.load`.
- Produces in `entities.py` (frozen dataclasses): `PestVector(id: int, name: str, guide: str, source: str)` and `PestCard(id: int, name: str, kind: str | None, photo_url: str | None, photo_source: str | None, description: str | None, occurrence: str | None, occurrence_source: str | None, vectors: tuple[PestVector, ...])`.
- Produces in `catalog_service.py`: `get_pest_card(pest_id: int) -> PestCard | None` (None for an unknown id). Photo, season and vector rows are indexed once (`functools.cache`) per pest.

- [ ] **Step 1: Write the failing tests** in `tests/test_catalog_pest_cards.py`
```python
from app.catalog.application import catalog_service as svc
from app.catalog.infrastructure.static_data import load


def raw(name):
    return load(name)


def season_of(pest_id, source):
    return next(s for s in raw("pest_season") if s["pest_id"] == pest_id and s["source"] == source)


def test_unknown_pest_is_none():
    assert svc.get_pest_card(999999) is None


def test_kind_is_mapped():
    assert svc.get_pest_card(8).kind == "병"
    assert svc.get_pest_card(48).kind == "해충"


def test_description_is_the_symptom_or_none():
    pest = next(p for p in raw("pest") if p["pest_id"] == 8)

    assert svc.get_pest_card(8).description == pest["symptom"]
    assert svc.get_pest_card(122).description is None


def test_photo_comes_from_the_pests_own_photos_and_crop():
    for pest in raw("pest"):
        card = svc.get_pest_card(pest["pest_id"])
        own = [p for p in raw("pest_photo") if p["pest_id"] == pest["pest_id"]]
        if own:
            assert card.photo_url == min(own, key=lambda p: p["photo_id"])["url"]
            assert card.photo_source == pest["photo_crop"]
        else:
            assert (card.photo_url, card.photo_source) == (None, None)


def test_pest_without_photo_has_null_photo_fields():
    card = svc.get_pest_card(24)

    assert (card.photo_url, card.photo_source) == (None, None)


def test_occurrence_from_a_pdf_row():
    card = svc.get_pest_card(8)

    assert card.occurrence == "6~7월 — 대관령 · 고랭지, 씨감자 · 예보"
    assert card.occurrence_source == "PDF 경보"


def test_occurrence_from_an_ncpms_row():
    card = svc.get_pest_card(101)

    assert card.occurrence == "4~7월 — " + season_of(101, "ncpms")["evidence"]
    assert card.occurrence_source == "NCPMS 설명"


def test_two_row_pests_use_the_ncpms_row():
    first, second = svc.get_pest_card(48), svc.get_pest_card(50)

    assert first.occurrence == "6, 8~9월 — " + season_of(48, "ncpms")["evidence"]
    assert second.occurrence == "4~6월 — " + season_of(50, "ncpms")["evidence"]
    assert (first.occurrence_source, second.occurrence_source) == ("NCPMS 설명", "NCPMS 설명")


def test_pest_without_season_has_null_occurrence():
    card = svc.get_pest_card(1)

    assert (card.occurrence, card.occurrence_source) == (None, None)


def test_virus_card_lists_its_vectors_by_name():
    card = svc.get_pest_card(66)

    assert [(v.id, v.name) for v in card.vectors] == [
        (87, "꽃노랑총채벌레"),
        (90, "대만총채벌레"),
        (115, "오이총채벌레"),
    ]
    row = next(v for v in raw("virus_vector") if v["virus_pest_id"] == 66 and v["vector_pest_id"] == 90)
    assert card.vectors[1].guide == row["guide_text"]
    assert card.vectors[1].source == row["evidence"]


def test_virus_without_a_vector_pest_has_no_vectors():
    assert svc.get_pest_card(64).vectors == ()


def test_non_virus_has_no_vectors():
    assert svc.get_pest_card(1).vectors == ()


def test_all_129_cards_build_with_the_expected_totals():
    cards = [svc.get_pest_card(p["pest_id"]) for p in raw("pest")]

    assert len(cards) == 129
    assert sum(c.photo_url is not None for c in cards) == 102
    assert sum(c.occurrence is not None for c in cards) == 49
    assert sum(bool(c.vectors) for c in cards) == 5
```
- [ ] **Step 2: Run** `.venv\Scripts\python -m pytest tests\test_catalog_pest_cards.py -q` — Expected: FAIL / collection ERROR on `get_pest_card`.
- [ ] **Step 3: Implement** the entities and `get_pest_card` per the interface block and constraints (use the Task 1 functions for photo, season, occurrence text and months).
- [ ] **Step 4: Run** the step 2 command — Expected: `13 passed`. Full suite and `ruff check .` clean (wrap the long `row = next(...)` line).
- [ ] **Step 5: Commit** `git add app/catalog tests/test_catalog_pest_cards.py` / `git commit -m "Add pest cards"`

### Task 3: Pest lists

**Files:**
- Modify: `app/catalog/application/catalog_service.py`
- Test: `tests/test_catalog_pest_lists.py`

**Interfaces:**
- Consumes: `get_pest_card` and the cached indexes (Task 2), `AppError`.
- Produces: `list_symptom_parts(crop_id: int) -> list[str]`; `list_candidates(crop_id: int, part: str) -> list[PestCard]`; `list_pests(crop_id: int, q: str | None = None) -> list[PestCard]`. Unknown crop → `AppError("NOT_FOUND", 404, <message>)` in all three; a `part` not in the crop's list → `AppError("VALIDATION_ERROR", 422, <message>, {"errors": [{"loc": ["query", "part"], "msg": <message>, "type": "value_error"}]})`.

- [ ] **Step 1: Write the failing tests** in `tests/test_catalog_pest_lists.py`
```python
import pytest

from app.catalog.application import catalog_service as svc
from app.catalog.infrastructure.static_data import load
from app.core.errors import AppError

PARTS = {
    1: ["덩이", "뿌리", "잎", "줄기", "벌레", "열매"],
    2: ["뿌리", "잎", "줄기", "벌레"],
    3: ["뿌리", "잎", "줄기", "벌레", "열매"],
}
CANDIDATES = {
    (1, "덩이"): 13, (1, "뿌리"): 3, (1, "잎"): 11, (1, "줄기"): 7, (1, "벌레"): 12, (1, "열매"): 1,
    (2, "잎"): 38, (2, "뿌리"): 8, (2, "줄기"): 16, (2, "벌레"): 27,
    (3, "뿌리"): 6, (3, "잎"): 36, (3, "줄기"): 26, (3, "열매"): 22, (3, "벌레"): 17,
}


def pests_of(crop_id):
    return [p for p in load("pest") if p["crop_id"] == crop_id]


def registered_ids():
    return {u["pest_id"] for u in load("pesticide_use")}


@pytest.mark.parametrize("crop_id", [1, 2, 3])
def test_symptom_parts_in_the_fixed_order(crop_id):
    assert svc.list_symptom_parts(crop_id) == PARTS[crop_id]


@pytest.mark.parametrize("key,count", CANDIDATES.items())
def test_candidate_counts_per_crop_and_part(key, count):
    assert len(svc.list_candidates(*key)) == count


def test_candidates_match_the_raw_parts():
    for (crop_id, part) in CANDIDATES:
        expected = {p["pest_id"] for p in pests_of(crop_id) if part in (p["parts"] or [])}

        assert {c.id for c in svc.list_candidates(crop_id, part)} == expected


def test_a_pest_with_several_parts_appears_under_each():
    for part in ("잎", "줄기", "덩이"):  # 역병(8)의 부위
        assert 8 in {c.id for c in svc.list_candidates(1, part)}


def test_candidates_are_sorted_by_name_without_duplicates():
    for (crop_id, part) in CANDIDATES:
        names = [c.name for c in svc.list_candidates(crop_id, part)]

        assert names == sorted(names)
        assert len({c.id for c in svc.list_candidates(crop_id, part)}) == len(names)


@pytest.mark.parametrize("crop_id,count", [(1, 25), (2, 43), (3, 23)])
def test_registered_pest_counts(crop_id, count):
    assert len(svc.list_pests(crop_id)) == count


def test_listed_pests_are_exactly_the_registered_pests_of_the_crop():
    for crop_id in (1, 2, 3):
        expected = {p["pest_id"] for p in pests_of(crop_id) if p["pest_id"] in registered_ids()}

        assert {c.id for c in svc.list_pests(crop_id)} == expected
        names = [c.name for c in svc.list_pests(crop_id)]
        assert names == sorted(names)


def test_registered_pests_without_a_pest_guide_entry_are_listed():
    no_doc = {p["pest_id"] for p in load("pest") if not p["has_doc"] and p["pest_id"] in registered_ids()}
    listed = {c.id for crop_id in (1, 2, 3) for c in svc.list_pests(crop_id)}

    assert no_doc and no_doc <= listed


def test_candidates_are_not_limited_to_registered_pests():
    candidates = {c.id for part in PARTS[3] for c in svc.list_candidates(3, part)}
    listed = {c.id for c in svc.list_pests(3)}

    assert len(candidates) == 43 and len(listed) == 23
    assert candidates - listed


def test_q_matches_a_name_substring():
    expected = sorted(p["name"] for p in pests_of(2) if "나방" in p["name"] and p["pest_id"] in registered_ids())

    assert [c.name for c in svc.list_pests(2, "나방")] == expected
    assert expected


def test_q_is_trimmed_and_blank_means_everything():
    everything = [c.id for c in svc.list_pests(2)]

    assert [c.id for c in svc.list_pests(2, "  나방 ")] == [c.id for c in svc.list_pests(2, "나방")]
    assert [c.id for c in svc.list_pests(2, "")] == everything
    assert [c.id for c in svc.list_pests(2, "   ")] == everything


def test_q_without_a_match_gives_an_empty_list():
    assert svc.list_pests(2, "없는이름") == []


@pytest.mark.parametrize(
    "call",
    [
        lambda: svc.list_symptom_parts(99),
        lambda: svc.list_candidates(99, "잎"),
        lambda: svc.list_pests(99),
    ],
    ids=["symptom-parts", "candidates", "pests"],
)
def test_unknown_crop_is_404(call):
    with pytest.raises(AppError) as info:
        call()

    assert (info.value.status, info.value.code) == (404, "NOT_FOUND")


@pytest.mark.parametrize("crop_id,part", [(1, "없는부위"), (3, "덩이"), (2, "열매")])
def test_part_outside_the_crops_list_is_422(crop_id, part):
    with pytest.raises(AppError) as info:
        svc.list_candidates(crop_id, part)

    assert (info.value.status, info.value.code) == (422, "VALIDATION_ERROR")
    error = info.value.details["errors"][0]
    assert error["loc"] == ["query", "part"]
    assert part not in error["msg"]
```
- [ ] **Step 2: Run** `.venv\Scripts\python -m pytest tests\test_catalog_pest_lists.py -q` — Expected: FAIL / collection ERROR on `list_symptom_parts`.
- [ ] **Step 3: Implement** the three functions per the interface block and constraints.
- [ ] **Step 4: Run** the step 2 command — Expected: `36 passed` (3 parts, 15 counts, 1 raw match, 1 multi-part, 1 sorted, 3 registered counts, 1 registered oracle, 1 no-guide, 1 not-limited, 3 q tests, 3 unknown-crop, 3 part errors). Full suite and `ruff check .` clean.
- [ ] **Step 5: Commit** `git add app/catalog/application/catalog_service.py tests/test_catalog_pest_lists.py` / `git commit -m "Add pest lists"`

### Task 4: Endpoints

**Files:**
- Modify: `app/catalog/presentation/schemas.py`, `app/catalog/presentation/router.py`
- Test: `tests/test_catalog_pest_api.py`

**Interfaces:**
- Consumes: Task 3 functions.
- Produces: `GET /crops/{crop_id}/symptom-parts` → `list[str]`; `GET /pests/candidates` (query `crop_id: int`, `part: str`) → `list[PestCardOut]`; `GET /pests` (query `crop_id: int`, `q: str | None`) → `list[PestCardOut]`; `PestCardOut` with the nine keys of the constraints and `VectorOut(id, name, guide, source)`; the existing router (already behind `current_user`) gets the three routes.

- [ ] **Step 1: Write the failing tests** in `tests/test_catalog_pest_api.py`
```python
import pytest

CARD_KEYS = {
    "id", "name", "kind", "photo_url", "photo_source", "description",
    "occurrence", "occurrence_source", "vectors",
}


def auth(uid):
    return {"X-User-Id": str(uid)}


@pytest.mark.parametrize(
    "path,params",
    [
        ("/crops/1/symptom-parts", {}),
        ("/pests/candidates", {"crop_id": 1, "part": "잎"}),
        ("/pests", {"crop_id": 1}),
    ],
)
def test_requires_authentication(client, path, params):
    r = client.get(path, params=params)

    assert (r.status_code, r.json()["error"]["code"]) == (401, "UNAUTHORIZED")


def test_symptom_parts_shape(client, make_user):
    r = client.get("/crops/3/symptom-parts", headers=auth(make_user("farmer")))

    assert (r.status_code, r.json()) == (200, ["뿌리", "잎", "줄기", "벌레", "열매"])


def test_candidates_shape(client, make_user):
    params = {"crop_id": 2, "part": "벌레"}
    r = client.get("/pests/candidates", params=params, headers=auth(make_user("farmer")))
    cards = r.json()

    assert r.status_code == 200
    assert len(cards) == 27
    assert all(set(c) == CARD_KEYS for c in cards)
    assert [c["name"] for c in cards] == sorted(c["name"] for c in cards)


def test_pests_list_and_filter(client, make_user):
    headers = auth(make_user("farmer"))
    everything = client.get("/pests", params={"crop_id": 2}, headers=headers).json()
    filtered = client.get("/pests", params={"crop_id": 2, "q": "나방"}, headers=headers).json()

    assert len(everything) == 43
    assert 0 < len(filtered) < len(everything)
    assert all("나방" in c["name"] for c in filtered)


def candidates(client, headers, crop_id, part):
    params = {"crop_id": crop_id, "part": part}
    return {c["id"]: c for c in client.get("/pests/candidates", params=params, headers=headers).json()}


def test_card_values_and_nulls(client, make_user):
    headers = auth(make_user("farmer"))
    with_data = candidates(client, headers, 1, "덩이")[8]  # 역병 (감자)
    plain = candidates(client, headers, 2, "잎")[24]  # 그루썩음병 (배추, 사진 없음)

    assert with_data["kind"] == "병"
    assert with_data["occurrence"] == "6~7월 — 대관령 · 고랭지, 씨감자 · 예보"
    assert with_data["occurrence_source"] == "PDF 경보"
    assert plain["photo_url"] is None and plain["photo_source"] is None
    assert (plain["occurrence"], plain["occurrence_source"], plain["vectors"]) == (None, None, [])


def test_vectors_shape(client, make_user):
    headers = auth(make_user("farmer"))
    cards = {}
    for part in ("뿌리", "잎", "줄기", "벌레", "열매"):
        cards |= candidates(client, headers, 3, part)
    virus = next(c for c in cards.values() if c["vectors"])

    assert all(set(v) == {"id", "name", "guide", "source"} for v in virus["vectors"])


@pytest.mark.parametrize(
    "path,params",
    [
        ("/crops/99/symptom-parts", {}),
        ("/pests/candidates", {"crop_id": 99, "part": "잎"}),
        ("/pests", {"crop_id": 99}),
    ],
)
def test_unknown_crop_is_404(client, make_user, path, params):
    r = client.get(path, params=params, headers=auth(make_user("farmer")))

    assert (r.status_code, r.json()["error"]["code"]) == (404, "NOT_FOUND")


def test_part_outside_the_crops_list_is_422_with_its_location(client, make_user):
    params = {"crop_id": 3, "part": "덩이"}
    r = client.get("/pests/candidates", params=params, headers=auth(make_user("farmer")))
    error = r.json()["error"]

    assert (r.status_code, error["code"]) == (422, "VALIDATION_ERROR")
    assert error["details"]["errors"][0]["loc"] == ["query", "part"]
    assert "덩이" not in str(error)


@pytest.mark.parametrize(
    "path,params",
    [("/pests/candidates", {"crop_id": 1}), ("/pests/candidates", {"part": "잎"}), ("/pests", {})],
)
def test_missing_query_values_are_422(client, make_user, path, params):
    r = client.get(path, params=params, headers=auth(make_user("farmer")))

    assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_ERROR")
```
- [ ] **Step 2: Run** `.venv\Scripts\python -m pytest tests\test_catalog_pest_api.py -q` — Expected: FAIL (the new routes answer 404/405 instead of the expected results).
- [ ] **Step 3: Implement** `VectorOut`, `PestCardOut` and the three routes (a small `_card_out` converter like the pesticide one).
- [ ] **Step 4: Run** the step 2 command — Expected: all pass (3 + 1 + 1 + 1 + 1 + 1 + 3 + 1 + 3 = 15). Full suite and `ruff check .` clean.
- [ ] **Step 5: Commit** `git add app/catalog/presentation tests/test_catalog_pest_api.py` / `git commit -m "Add pest endpoints"`
- [ ] **Step 6: Mutation checks.** (a) In `list_candidates` also require the pest to be registered, run `tests\test_catalog_pest_lists.py` — Expected: the candidate-count and `test_candidates_are_not_limited_to_registered_pests` cases FAIL; restore with `git checkout -- app/catalog/application/catalog_service.py`. (b) In `pick_season` swap the preference to `pdf` first, run `tests\test_catalog_pest_rules.py tests\test_catalog_pest_cards.py` — Expected: `test_pick_season_prefers_ncpms_then_pdf_then_none` and `test_two_row_pests_use_the_ncpms_row` FAIL; restore with `git checkout -- app/catalog/domain/pest_rules.py`. Re-run the whole suite — all pass; `git status --short` clean.

### Task 5: Final verification

- [ ] **Step 1:** `.venv\Scripts\python -m pytest -q -rs` and `.venv\Scripts\ruff check .` — Expected: all pass, `All checks passed!`.
- [ ] **Step 2:** `git diff --name-only origin/test..HEAD` lists no `팜가디언_API_명세.md`; `git status -sb` clean; `git log --oneline origin/test..HEAD` shows 5 commits. Do not push.
- [ ] **Step 3:** Tell the user: BE-36 done; next BE-46/47 (spray records), then BE-45 (judgment API). Notion rows to update after the PR merges: 증상 부위 목록 조회, 병해충 후보 조회, 병해충 목록·이름 검색.
