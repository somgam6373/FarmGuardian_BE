# Catalog Read Service, `GET /crops`, `GET /pesticides` Implementation Plan (BE-37)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (project CLAUDE.md: no subagent-driven execution). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `GET /crops` and `GET /pesticides` served from the static catalog data through a cached read service, in the shape of the API spec.

**Architecture:** `app/catalog/domain/entities.py` (frozen dataclasses), `app/catalog/application/catalog_service.py` (functions over `static_data.load`, cached drug index), `app/catalog/presentation/` (router + response schemas), registered in `app/main.py`. Both endpoints depend on `current_user`.

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, pytest (`client`, `make_user` fixtures for the API tests).

**Spec:** `docs/dev/2026-10-29-catalog-pesticides-design.md` (approved in chat 2026-10-29); frame = `docs/dev/팜가디언_API_명세.md` (never edited).

## Global Constraints

- `팜가디언_API_명세.md` is the frame and **must not change**: no commit of this plan touches it.
- `GET /pesticides` items have exactly the keys `id, name, item_name, moa, at_planting_only`; `moa` is `null` or `{label_kr, system, code}`. `name` = brand (`brand`), `item_name` = item (`product`).
- Drug identity: (`product`, `brand`) pair; `id` = smallest `use_id` of the pair over all crops (1,363 drugs).
- `moa`: `moa_code` None → null; single code → looked up in `moa.json`, `label_kr` = the code, `system`/`code` = `intl_code` split at the first space (null when `intl_code` is empty); compound code (`+`) → `label_kr` = the code, `system`/`code` null.
- A list holds drugs with at least one row on a pest of the crop (only rows of `pest_id` when given); `at_planting_only` = all those rows have `parse_status == "stage"`.
- Order: `moa.label_kr` ascending with `moa` null last, then `item_name`, then `name`.
- Errors in the common format: unknown `crop_id`, unknown `pest_id`, or a pest of another crop → 404 `NOT_FOUND`; missing/non-integer query value → 422; no `X-User-Id` → 401.
- No database access in the service; no change to `schema.sql`.
- Code and identifiers in English, short Korean comments as in `app/core`; ruff line length 100 (Korean characters count double, wrap long strings); tests flat in `tests/`; commit messages in English; do not push.

## Review Focus

- `at_planting_only` depends on the crop (and pest): it is checked against an independent computation from the raw rows for all three crops, not only against pinned counts. (Task 1)
- The id of a drug is the same in every list and equals its smallest `use_id` (`아미설브롬 입상수화제` / `엑사이도` → 1); ids are unique inside a list. (Task 1)
- Sorting is deterministic and puts drugs without `moa` last. (Task 1)
- A pest of another crop is a 404, not an empty list. (Tasks 1, 2)
- Both endpoints refuse requests without `X-User-Id`, and the JSON keys are exactly those of the spec. (Task 2)

---

### Task 0: Commit the design and this plan

- [ ] **Step 1:** `git add docs/dev/2026-10-29-catalog-pesticides-design.md docs/dev/2026-10-29-catalog-pesticides-plan.md` / `git commit -m "Add catalog pesticides design and plan"`

### Task 1: Entities and read service

**Files:**
- Create: `app/catalog/domain/__init__.py`, `app/catalog/domain/entities.py`, `app/catalog/application/__init__.py`, `app/catalog/application/catalog_service.py` (the `__init__.py` files empty, like the other packages)
- Test: `tests/test_catalog_service.py`

**Interfaces:**
- Produces in `entities.py` (frozen dataclasses): `Crop(id: int, name: str)`, `Moa(label_kr: str, system: str | None, code: str | None)`, `Pesticide(id: int, name: str, item_name: str, moa: Moa | None)`, `PesticideEntry(pesticide: Pesticide, at_planting_only: bool)`.
- Produces in `catalog_service.py`: `list_crops() -> list[Crop]` (ordered by `id`); `list_pesticides(crop_id: int, pest_id: int | None = None) -> list[PesticideEntry]` (sorted per the constraints; raises `AppError("NOT_FOUND", 404, <message>)` from `app.core.errors` for an unknown crop, an unknown pest or a pest of another crop); the drug index is built once (`functools.cache`) from `static_data.load("pesticide_use")`, `"safe_use_std"`, `"pest"`, `"moa"`, `"crop"`.

- [ ] **Step 1: Write the failing tests** in `tests/test_catalog_service.py`
```python
import pytest

from app.catalog.application import catalog_service as svc
from app.catalog.domain.entities import Moa
from app.catalog.infrastructure.static_data import load
from app.core.errors import AppError

CROPS = [1, 2, 3]


def pair(entry):
    return (entry.pesticide.item_name, entry.pesticide.name)


def all_entries():
    return [e for crop_id in CROPS for e in svc.list_pesticides(crop_id)]


def raw_flags(crop_id, pest_id=None):  # 원본 행에서 직접 계산한 기준: (품목, 상표) → 심을 때만 여부
    pests = {p["pest_id"]: p["crop_id"] for p in load("pest")}
    status = {s["use_id"]: s["parse_status"] for s in load("safe_use_std")}
    rows = {}
    for u in load("pesticide_use"):
        if pests[u["pest_id"]] != crop_id or (pest_id and u["pest_id"] != pest_id):
            continue
        rows.setdefault((u["product"], u["brand"]), []).append(status[u["use_id"]])
    return {key: all(s == "stage" for s in found) for key, found in rows.items()}


def test_crops_in_id_order():
    assert [(c.id, c.name) for c in svc.list_crops()] == [(1, "감자"), (2, "배추"), (3, "토마토")]


@pytest.mark.parametrize("crop_id,count", [(1, 508), (2, 1008), (3, 515)])
def test_drug_counts_per_crop(crop_id, count):
    assert len(svc.list_pesticides(crop_id)) == count


def test_ids_are_unique_inside_a_list():
    for crop_id in CROPS:
        ids = [e.pesticide.id for e in svc.list_pesticides(crop_id)]
        assert len(set(ids)) == len(ids)


def test_id_is_the_smallest_use_id_of_the_pair():
    first = next(e for e in svc.list_pesticides(1) if pair(e) == ("아미설브롬 입상수화제", "엑사이도"))

    assert first.pesticide.id == 1


@pytest.mark.parametrize("crop_id,only,no_moa", [(1, 103, 3), (2, 171, 4), (3, 57, 5)])
def test_at_planting_only_and_missing_moa_counts(crop_id, only, no_moa):
    entries = svc.list_pesticides(crop_id)

    assert sum(e.at_planting_only for e in entries) == only
    assert sum(e.pesticide.moa is None for e in entries) == no_moa


def test_at_planting_only_matches_the_raw_rows_for_every_crop():
    for crop_id in CROPS:
        got = {pair(e): e.at_planting_only for e in svc.list_pesticides(crop_id)}

        assert got == raw_flags(crop_id)


@pytest.mark.parametrize("crop_id", CROPS)
def test_sort_order(crop_id):
    keys = [
        (
            e.pesticide.moa is None,
            e.pesticide.moa.label_kr if e.pesticide.moa else "",
            e.pesticide.item_name,
            e.pesticide.name,
        )
        for e in svc.list_pesticides(crop_id)
    ]

    assert keys == sorted(keys)


def test_moa_conversion_samples():
    entries = all_entries()
    by_label = {e.pesticide.moa.label_kr: e.pesticide.moa for e in entries if e.pesticide.moa}

    assert by_label["가1"] == Moa(label_kr="가1", system="FRAC", code="4")
    assert by_label["카"] == Moa(label_kr="카", system="FRAC", code="M 01~M 13")
    compound = next(m for label, m in by_label.items() if "+" in label)
    assert (compound.system, compound.code) == (None, None)
    no_intl = [m for m in by_label.values() if m.system is None and "+" not in m.label_kr]
    assert no_intl  # 국제 코드가 없는 단일 계열은 system·code가 null이다
    assert any(e.pesticide.moa is None for e in entries)


def test_pest_filter_narrows_the_list_and_keeps_ids():
    everything = {pair(e): e for e in svc.list_pesticides(1)}
    narrowed = svc.list_pesticides(1, 1)
    expected = {(u["product"], u["brand"]) for u in load("pesticide_use") if u["pest_id"] == 1}

    assert {pair(e) for e in narrowed} == expected
    assert len(narrowed) < len(everything)
    assert all(everything[pair(e)].pesticide.id == e.pesticide.id for e in narrowed)
    assert {pair(e): e.at_planting_only for e in narrowed} == raw_flags(1, 1)


def raises_not_found(*args):
    with pytest.raises(AppError) as info:
        svc.list_pesticides(*args)
    assert (info.value.status, info.value.code) == (404, "NOT_FOUND")


def test_unknown_crop_is_404():
    raises_not_found(99)


def test_unknown_pest_is_404():
    raises_not_found(1, 999999)


def test_pest_of_another_crop_is_404():
    other = next(p["pest_id"] for p in load("pest") if p["crop_id"] == 2)

    raises_not_found(1, other)
```
- [ ] **Step 2: Run** `.venv\Scripts\python -m pytest tests\test_catalog_service.py -q` — Expected: collection ERROR `No module named 'app.catalog.application'`.
- [ ] **Step 3: Implement** the entities and the service per the interface block and constraints. Build the index once: for every `pesticide_use` row, group by (`product`, `brand`) keeping the smallest `use_id`, the single `moa_code`, and per crop and pest the `parse_status` rows.
- [ ] **Step 4: Run** the step 2 command — Expected: `18 passed` (1 crops, 3 counts, 1 ids, 1 id rule, 3 flag counts, 1 flag oracle, 3 sort orders, 1 moa samples, 1 pest filter, 3 errors). Full suite and `ruff check .` clean (wrap long lines).
- [ ] **Step 5: Commit** `git add app/catalog tests/test_catalog_service.py` / `git commit -m "Add catalog read service"`

### Task 2: Endpoints

**Files:**
- Create: `app/catalog/presentation/__init__.py` (empty), `app/catalog/presentation/schemas.py`, `app/catalog/presentation/router.py`
- Modify: `app/main.py`
- Test: `tests/test_catalog_api.py`

**Interfaces:**
- Consumes: `catalog_service` (Task 1), `current_user` (`app/core/auth.py`).
- Produces: `GET /crops` → `list[CropOut]` (`id`, `name`); `GET /pesticides` with query `crop_id: int` (required) and `pest_id: int | None` → `list[PesticideOut]` (`id`, `name`, `item_name`, `moa: MoaOut | None`, `at_planting_only: bool`), `MoaOut` = `label_kr`, `system`, `code`; both routes use `dependencies=[Depends(current_user)]`; the router is included in `app/main.py` like the farm router.

- [ ] **Step 1: Write the failing tests** in `tests/test_catalog_api.py`
```python
def auth(uid):
    return {"X-User-Id": str(uid)}


def test_crops_requires_authentication(client):
    r = client.get("/crops")

    assert (r.status_code, r.json()["error"]["code"]) == (401, "UNAUTHORIZED")


def test_pesticides_requires_authentication(client):
    r = client.get("/pesticides", params={"crop_id": 1})

    assert (r.status_code, r.json()["error"]["code"]) == (401, "UNAUTHORIZED")


def test_crops_shape(client, make_user):
    r = client.get("/crops", headers=auth(make_user("farmer")))

    assert r.status_code == 200
    assert r.json() == [
        {"id": 1, "name": "감자"},
        {"id": 2, "name": "배추"},
        {"id": 3, "name": "토마토"},
    ]


def test_pesticides_shape(client, make_user):
    r = client.get("/pesticides", params={"crop_id": 2}, headers=auth(make_user("farmer")))
    items = r.json()

    assert r.status_code == 200
    assert len(items) == 1008
    assert all(set(i) == {"id", "name", "item_name", "moa", "at_planting_only"} for i in items)
    assert all(isinstance(i["at_planting_only"], bool) for i in items)
    assert len({i["id"] for i in items}) == len(items)
    with_moa = [i["moa"] for i in items if i["moa"] is not None]
    assert with_moa and all(set(m) == {"label_kr", "system", "code"} for m in with_moa)
    assert any(i["moa"] is None for i in items)


def test_pest_filter_narrows_the_list(client, make_user):
    headers = auth(make_user("farmer"))
    all_items = client.get("/pesticides", params={"crop_id": 1}, headers=headers).json()
    narrowed = client.get("/pesticides", params={"crop_id": 1, "pest_id": 1}, headers=headers)

    assert narrowed.status_code == 200
    assert 0 < len(narrowed.json()) < len(all_items)


def test_unknown_crop_is_404(client, make_user):
    r = client.get("/pesticides", params={"crop_id": 99}, headers=auth(make_user("farmer")))

    assert (r.status_code, r.json()["error"]["code"]) == (404, "NOT_FOUND")


def test_unknown_pest_is_404(client, make_user):
    params = {"crop_id": 1, "pest_id": 999999}
    r = client.get("/pesticides", params=params, headers=auth(make_user("farmer")))

    assert (r.status_code, r.json()["error"]["code"]) == (404, "NOT_FOUND")


def test_pest_of_another_crop_is_404(client, make_user):
    from app.catalog.infrastructure.static_data import load

    other = next(p["pest_id"] for p in load("pest") if p["crop_id"] == 2)
    r = client.get(
        "/pesticides",
        params={"crop_id": 1, "pest_id": other},
        headers=auth(make_user("farmer")),
    )

    assert (r.status_code, r.json()["error"]["code"]) == (404, "NOT_FOUND")


def test_missing_or_bad_crop_id_is_422(client, make_user):
    headers = auth(make_user("farmer"))

    for params in ({}, {"crop_id": "abc"}):
        r = client.get("/pesticides", params=params, headers=headers)

        assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_ERROR")
```
(move the inline `load` import to the top of the file in the real test; keep ruff's import order.)
- [ ] **Step 2: Run** `.venv\Scripts\python -m pytest tests\test_catalog_api.py -q` — Expected: the tests FAIL with 404 for the missing routes (or an `AssertionError` on the status codes).
- [ ] **Step 3: Implement** `schemas.py` and `router.py` and include the router in `app/main.py`.
- [ ] **Step 4: Run** the step 2 command — Expected: `9 passed`. Full suite and `ruff check .` clean.
- [ ] **Step 5: Commit** `git add app/catalog/presentation app/main.py tests/test_catalog_api.py` / `git commit -m "Add crops and pesticides endpoints"`
- [ ] **Step 6: Mutation check.** In the service change the sort key so drugs without `moa` come first, run `tests\test_catalog_service.py` — Expected: the three `test_sort_order` cases FAIL; restore with `git checkout -- app/catalog/application/catalog_service.py`; re-run — `18 passed`; `git status --short` clean.

### Task 3: Final verification

- [ ] **Step 1:** `.venv\Scripts\python -m pytest -q -rs` and `.venv\Scripts\ruff check .` — Expected: all pass, `All checks passed!`.
- [ ] **Step 2:** `git diff --name-only origin/test..HEAD` lists no `팜가디언_API_명세.md`; `git status -sb` clean; `git log --oneline origin/test..HEAD` shows 3 commits. Do not push.
- [ ] **Step 3:** Tell the user: BE-37 done (crops, drug list, drug identity); next BE-36 (symptom parts, pest candidates, pest list), then BE-46/47 (spray records) and BE-45 (judgment API).
