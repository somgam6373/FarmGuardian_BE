# Farmmap `parcel_by_id` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (project CLAUDE.md: no subagent-driven execution). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `parcel_by_id(farmmap_id)` fetches one Farmmap parcel by id (or `None`), sharing the request code with `parcels_by_pnu`.

**Architecture:** Extend `app/farm/infrastructure/integrations/farmmap.py`: extract a private `_fetch` helper from `parcels_by_pnu`, add `ID_URL` and `parcel_by_id`. Reuse `parse_farmmap_response`.

**Tech Stack:** Python 3.13 (venv 3.14), `httpx2`, pytest + `httpx2.MockTransport`.

**Spec:** `docs/dev/2026-10-29-parcel-by-id-design.md`

## Global Constraints

- Branch `feat/hb-parcel-by-id` (from `test`, after PR #1). Commit messages in English.
- URL `http://apis.data.go.kr/B552895/getFarmmapService/getIdBasedFarmmapInfo`, params `serviceKey`, `type=xml`, `id`; timeout 5 s; no retry.
- Errors as `parcels_by_pnu`: `AppError("UPSTREAM_ERROR", 502, …, {"source": "farmmap"[, "upstream_code"]})`.
- Fixture already in place: `tests/fixtures/farmmap_id_418203252100637.xml` (live, 1 item `161-3전` 밭).
- Ruff line length 100, rules E/F/I.

## Review Focus

- Farmmap returns the requested parcel plus others → the requested one is returned. (Task 1)
- Id with surrounding whitespace or empty string → sent as-is, `resultCode 3` → `None` (no crash). (Task 1: empty-string case via MockTransport returning code 3)
- `parcels_by_pnu` behaviour unchanged after the refactor → its existing tests still pass untouched. (Task 1)

---

### Task 1: `parcel_by_id`

**Files:**
- Modify: `app/farm/infrastructure/integrations/farmmap.py`
- Add: `tests/fixtures/farmmap_id_418203252100637.xml` (already copied)
- Test: `tests/test_farmmap_client.py`

**Interfaces:**
- Produces: `parcel_by_id(farmmap_id: str, *, client: httpx2.Client | None = None) -> FarmmapParcel | None`; private `_fetch(url: str, params: dict, client: httpx2.Client | None) -> list[FarmmapParcel]`.

- [ ] **Step 1: Write failing tests** in `tests/test_farmmap_client.py`

```python
def test_by_id_sends_key_type_and_id():        # path ends with /getIdBasedFarmmapInfo; params serviceKey, type=xml, id=ID; fixture → parcel
def test_by_id_returns_the_parcel():           # fixture → farmmap_id "418203252100637", lnm "161-3전", land_use "밭"
def test_by_id_no_data_is_none():              # code 3, no body → None
def test_by_id_empty_id_is_none():             # parcel_by_id("") with handler returning code 3 → None
def test_by_id_other_parcel_only_is_none():    # PNU fixture filtered to the 160-7 item only (farmmap_id 418203252100655) → None
def test_by_id_picks_requested_among_many():   # PNU fixture (2 items) requested "418203252100655" → that parcel
def test_by_id_gateway_403_maps_to_reason_code():  # → 502, {"source": "farmmap", "upstream_code": "30"}
def test_by_id_timeout_maps_to_upstream_error():   # httpx2.ReadTimeout → 502, {"source": "farmmap"}
```

- [ ] **Step 2:** `pytest tests/test_farmmap_client.py -q` → FAIL (ImportError on `parcel_by_id`)
- [ ] **Step 3:** Extract `_fetch` from `parcels_by_pnu` (HTTP call, default client with 5 s timeout, `httpx2.HTTPError` → 502, then `parse_farmmap_response(response.text)`); `parcels_by_pnu` calls it with `PNU_URL`. Add `ID_URL` and `parcel_by_id` returning the first parcel whose `farmmap_id == farmmap_id`, else `None`.
- [ ] **Step 4:** `pytest -q` → all PASS (existing `parcels_by_pnu` tests unchanged); `ruff check .` clean
- [ ] **Step 5:** Manual: `parcel_by_id("418203252100637")` against live Farmmap → `161-3전`; `parcel_by_id("999999999999999")` → `None`.
- [ ] **Step 6:** Commit `Add Farmmap parcel lookup by id`
