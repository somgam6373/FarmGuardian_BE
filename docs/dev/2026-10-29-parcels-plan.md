# GET /parcels Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (project CLAUDE.md: no subagent-driven execution). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `GET /parcels?pnu=` calls Farmmap, parses its XML and returns `[Parcel]` per the API spec.

**Architecture:** DDD layers inside `app/farm`: pure area math in `domain`, Farmmap HTTP client + pure XML parser in `infrastructure/integrations`, `find_parcels` use case in `application`, FastAPI router + pydantic schema in `presentation`. No DB.

**Tech Stack:** Python 3.13, FastAPI, httpx (sync), `xml.etree.ElementTree`, pytest + `httpx.MockTransport`.

**Spec:** `docs/dev/2026-10-29-parcels-design.md`

## Global Constraints

- Errors use `AppError(code, status, message, details)` from `app/core/errors.py`; upstream failures are `AppError("UPSTREAM_ERROR", 502, …, {"source": "farmmap"} | {"source": "farmmap", "upstream_code": str})`.
- Farmmap URL: `http://apis.data.go.kr/B552895/getFarmmapService/getPnuBasedFarmmapInfo`, params `serviceKey`, `type=xml`, `pnuCode`; timeout 5 s; no retry.
- Success codes `"0"` and `"00"`; `"3"` = empty result. `<totalCount>` is never read.
- The request URL (contains the key) is never logged: `logging.getLogger("httpx").setLevel(logging.WARNING)` in `farmmap.py`.
- GeoJSON coordinates rounded to 1 decimal; `area_m2` computed on unrounded coordinates, rounded to 1 decimal.
- Code, identifiers and docs in English; comments match existing style (short Korean comments are used in `app/core`). Ruff line length 100, rules E/F/I.
- Tests are flat files in `tests/` (existing style); fixtures in `tests/fixtures/`.

## Review Focus

- A parcel whose `MultiPolygon` has 2+ `polygonMember`s → all pieces parsed, area summed. (Task 2, Task 1)
- `gml:coordinates` text with leading/trailing newlines and indentation (real responses have them) → parsed without empty points. (Task 2)
- Non-XML body (HTML error page) with HTTP 200 or 5xx → 502 without `upstream_code`. (Task 3)
- `vdptYr` as `2022`, `2022-04-01`, empty element, or missing → `2022`, `2022`, `None`, `None`. (Task 2)
- `resultCode 3` with no `<body>` element at all → `[]`. (Task 2)

---

### Task 0: Local environment

- [ ] **Step 1:** `python -m venv .venv` then `.venv\Scripts\python -m pip install -r requirements-dev.txt`
- [ ] **Step 2:** Run `.venv\Scripts\python -m pytest` — Expected: existing tests PASS. (If `TestClient` fails to import `httpx`, note it; Task 3 adds `httpx` to `requirements.txt`.)

No commit.

### Task 1: Polygon area (domain)

**Files:**
- Create: `app/farm/__init__.py`, `app/farm/domain/__init__.py`, `app/farm/domain/geometry.py`
- Test: `tests/test_farm_geometry.py`

**Interfaces:**
- Produces: type aliases `Ring = list[tuple[float, float]]`, `Polygon = list[Ring]` (first ring outer, rest holes), `MultiPolygon = list[Polygon]`; `multipolygon_area(polygons: MultiPolygon) -> float` (m², unrounded, always positive regardless of ring orientation).

- [ ] **Step 1: Write failing tests**

```python
SQUARE = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)]
HOLE = [(4.0, 4.0), (6.0, 4.0), (6.0, 6.0), (4.0, 6.0), (4.0, 4.0)]

def test_square_area():            assert multipolygon_area([[SQUARE]]) == 100
def test_reversed_ring_is_positive(): assert multipolygon_area([[SQUARE[::-1]]]) == 100
def test_hole_is_subtracted():     assert multipolygon_area([[SQUARE, HOLE]]) == 96
def test_pieces_are_summed():      assert multipolygon_area([[SQUARE], [SQUARE]]) == 200
```

- [ ] **Step 2:** `pytest tests/test_farm_geometry.py -v` → FAIL (import error)
- [ ] **Step 3:** Implement with the shoelace formula: `abs(outer) - sum(abs(hole))` per polygon, summed.
- [ ] **Step 4:** `pytest tests/test_farm_geometry.py -v` → PASS
- [ ] **Step 5:** Commit `Add polygon area for farm geometry`

### Task 2: Farmmap XML parser

**Files:**
- Create: `app/farm/infrastructure/__init__.py`, `app/farm/infrastructure/integrations/__init__.py`, `app/farm/infrastructure/integrations/farmmap.py`
- Create: `tests/fixtures/farmmap_pnu_4182032521101610003.xml` (copy of the live response saved 2026-10-29 at `<scratchpad>/farmmap_161-3.xml`)
- Test: `tests/test_farmmap_parser.py`

**Interfaces:**
- Consumes: `Polygon`, `MultiPolygon` from Task 1.
- Produces:
  - `@dataclass(frozen=True) FarmmapParcel(farmmap_id: str, pnu: str, lnm: str, land_use: str, vdpt_yr: int | None, polygons: MultiPolygon)`
  - `parse_farmmap_response(xml: str) -> list[FarmmapParcel]` — pure; raises `AppError("UPSTREAM_ERROR", 502, …)` for: non-XML text, unknown root, `resultCode` not in `{"0","00","3"}` (`upstream_code` = code), gateway root `OpenAPI_ServiceResponse` (`upstream_code` = `cmmMsgHeader/returnReasonCode`), malformed `<item>` (no `upstream_code`).

- [ ] **Step 1: Write failing tests** (hand-written XML lives in the test file as small strings built by a helper `_response(code, items_xml)` / `_item(...)`)

```python
def test_live_fixture_parses_two_parcels():
    parcels = parse_farmmap_response(FIXTURE.read_text(encoding="utf-8"))
    assert [(p.farmmap_id, p.pnu, p.lnm, p.land_use, p.vdpt_yr) for p in parcels] == [
        ("418203252100637", "4182032521101610003", "161-3전", "밭", 2022),
        ("418203252100655", "4182032521101600007", "160-7답", "논", 2020),
    ]
    assert len(parcels[0].polygons) == 1 and len(parcels[0].polygons[0]) == 1   # 1 piece, no hole
    assert parcels[0].polygons[0][0][0] == (993833.485624643, 1970344.5561137851)
    assert parcels[0].polygons[0][0][0] == parcels[0].polygons[0][0][-1]         # closed ring

def test_code_00_is_success(): ...          # one item → 1 parcel
def test_code_3_without_body_is_empty():    assert parse_farmmap_response(_response("3", None)) == []
def test_other_code_raises_with_upstream_code():   # "22" → AppError status 502, details == {"source": "farmmap", "upstream_code": "22"}
def test_gateway_error_raises_with_reason_code():  # OpenAPI_ServiceResponse/cmmMsgHeader/returnReasonCode 30 → upstream_code "30"
def test_non_xml_raises_without_upstream_code():   # "<html>oops" → details == {"source": "farmmap"}
def test_item_without_geometry_raises():           # details == {"source": "farmmap"}
def test_inner_boundary_is_hole():                 # polygons[0] has 2 rings
def test_multiple_polygon_members():               # 2 polygonMember → len(polygons) == 2
def test_coordinates_with_whitespace():            # "\n   0,0 10,0  10,10 0,10 0,0\n  " → 5 points
@pytest.mark.parametrize("raw, year", [("2022", 2022), ("2022-04-01", 2022), ("", None), (None, None)])
def test_vdpt_yr(raw, year): ...                   # None = element absent
```

- [ ] **Step 2:** `pytest tests/test_farmmap_parser.py -v` → FAIL
- [ ] **Step 3:** Implement with `xml.etree.ElementTree`; GML namespace `http://www.opengis.net/gml`. Polygon = `outerBoundaryIs/LinearRing/coordinates` + each `innerBoundaryIs/LinearRing/coordinates`; coordinates = `text.split()` then `x,y` pairs. `vdpt_yr = int(text[:4])` when the first 4 chars are digits, else `None`.
- [ ] **Step 4:** `pytest tests/test_farmmap_parser.py -v` → PASS
- [ ] **Step 5:** Commit `Add Farmmap XML parser`

### Task 3: Farmmap HTTP client and config

**Files:**
- Modify: `app/farm/infrastructure/integrations/farmmap.py`, `app/core/config.py`, `tests/conftest.py`, `.env.example`, `requirements.txt`
- Test: `tests/test_farmmap_client.py`

**Interfaces:**
- Consumes: `parse_farmmap_response`, `FarmmapParcel` (Task 2).
- Produces: `parcels_by_pnu(pnu: str, *, client: httpx.Client | None = None) -> list[FarmmapParcel]` (default client: `httpx.Client(timeout=5)`); `settings.farmmap_api_key: str`.

- [ ] **Step 1: Write failing tests** with `httpx.Client(transport=httpx.MockTransport(handler))`

```python
def test_sends_key_type_and_pnu():          # handler asserts url path ends with getPnuBasedFarmmapInfo,
                                            # params serviceKey == settings.farmmap_api_key, type == "xml",
                                            # pnuCode == "4182032521101610003"; returns fixture → 2 parcels
def test_gateway_403_maps_to_reason_code():  # 403 + OpenAPI_ServiceResponse body → upstream_code "30"
def test_html_500_maps_to_upstream_error():  # 500 + "<html>" → 502, details == {"source": "farmmap"}
def test_timeout_maps_to_upstream_error():   # handler raises httpx.ReadTimeout → 502, {"source": "farmmap"}
def test_connect_error_maps_to_upstream_error():  # httpx.ConnectError → same
```

- [ ] **Step 2:** `pytest tests/test_farmmap_client.py -v` → FAIL
- [ ] **Step 3:** Add `farmmap_api_key: str` to `Settings`; `os.environ.setdefault("FARMMAP_API_KEY", "test-farmmap-key")` in `tests/conftest.py`; `FARMMAP_API_KEY=` line to `.env.example`; `httpx>=0.28` to `requirements.txt`. Implement `parcels_by_pnu`: any `httpx.HTTPError` → `AppError` 502 `{"source": "farmmap"}`; otherwise pass `response.text` to the parser regardless of HTTP status (gateway errors come as 403 with a parsable body).
- [ ] **Step 4:** `pytest -v` → all PASS
- [ ] **Step 5:** Commit `Add Farmmap client for PNU lookup`

### Task 4: GET /parcels

**Files:**
- Create: `app/farm/application/__init__.py`, `app/farm/application/field_service.py`, `app/farm/presentation/__init__.py`, `app/farm/presentation/schemas.py`, `app/farm/presentation/router.py`
- Modify: `app/main.py` (`app.include_router(farm_router)`)
- Test: `tests/test_parcels_api.py`

**Interfaces:**
- Consumes: `farmmap.parcels_by_pnu` (called as module attribute `farmmap.parcels_by_pnu(...)` so tests can monkeypatch it), `multipolygon_area` (Task 1).
- Produces:
  - `find_parcels(pnu: str) -> list[dict]` — keys exactly the `Parcel` fields: `farmmap_id, pnu, lnm, land_use, vdpt_yr, area_m2, geometry, matches_query, used_by_field_id`.
  - `schemas.Parcel` (pydantic) with those fields; `geometry: dict` (`{"type": "MultiPolygon", "coordinates": [[[[x, y], ...]]]}`).
  - `router` with `GET /parcels`, `pnu: str = Query(pattern=r"^\d{19}$")`, `response_model=list[Parcel]`, no auth.

- [ ] **Step 1: Write failing tests** (monkeypatch `app.farm.infrastructure.integrations.farmmap.parcels_by_pnu` to return two `FarmmapParcel`s: a 10×10 square with pnu = query, and one with a different pnu)

```python
def test_returns_spec_shaped_parcels():
    r = client.get("/parcels", params={"pnu": PNU})
    assert r.status_code == 200
    first, second = r.json()
    assert first == {"farmmap_id": "1", "pnu": PNU, "lnm": "161-3전", "land_use": "밭", "vdpt_yr": 2022,
                     "area_m2": 100.0, "matches_query": True, "used_by_field_id": None,
                     "geometry": {"type": "MultiPolygon", "coordinates": [[[[0.0, 0.0], [10.0, 0.0], ...]]]}}
    assert second["matches_query"] is False

def test_coordinates_rounded_to_one_decimal():   # 0.04 → 0.0, 993833.485 → 993833.5
@pytest.mark.parametrize("pnu", ["123", "418203252110161000a", "41820325211016100031"])
def test_bad_pnu_is_validation_error(pnu):      # 422, error.code == "VALIDATION_ERROR", stub not called
def test_missing_pnu_is_validation_error():     # 422
def test_upstream_error_is_502():               # stub raises AppError 502 → body error.code == "UPSTREAM_ERROR", details.source == "farmmap"
def test_no_auth_header_needed():               # covered by the above requests having no X-User-Id
```

- [ ] **Step 2:** `pytest tests/test_parcels_api.py -v` → FAIL
- [ ] **Step 3:** Implement service, schema, router; include router in `app/main.py`.
- [ ] **Step 4:** `pytest -v` and `ruff check .` → all PASS, no lint errors
- [ ] **Step 5:** Manual check: `uvicorn app.main:app --reload`, open `http://localhost:8000/parcels?pnu=4182032521101610003` → 2 parcels from live Farmmap.
- [ ] **Step 6:** Commit `Add GET /parcels endpoint`
