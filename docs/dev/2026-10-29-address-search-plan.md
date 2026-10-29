# GET /addresses/search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (project CLAUDE.md: no subagent-driven execution). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `GET /addresses/search?keyword&page` returns lots (`jibun_addr`, `pnu`) from VWorld search, and the API spec / architecture doc describe VWorld instead of juso.

**Architecture:** Same layering as `GET /parcels`: VWorld client in `farm/infrastructure/integrations/vworld.py`, `search_addresses` in `field_service.py`, route + schemas in `farm/presentation`. Keyword validation happens in the presentation layer so invalid input never reaches VWorld.

**Tech Stack:** Python 3.13 (venv 3.14), FastAPI, `httpx2` (sync), pydantic `AfterValidator`, pytest + `httpx2.MockTransport`.

**Spec:** `docs/dev/2026-10-29-address-search-design.md`

## Global Constraints

- Branch `feat/hb-address-search` (stacked on `feat/hb-parcels`). Commit messages in English.
- Upstream failures: `AppError("UPSTREAM_ERROR", 502, …, {"source": "vworld"} | {"source": "vworld", "upstream_code": str})`.
- VWorld URL `https://api.vworld.kr/req/search`; params `service=search`, `request=search`, `version=2.0`, `type=address`, `category=parcel`, `crs=epsg:5179`, `format=json`, `size=10`, `page`, `query`, `key`; timeout 5 s; no retry.
- Keyword rule: trimmed, 2–80 chars, only `[가-힣0-9 \-]`, at least one `[가-힣]`. Page 1–1000, default 1.
- Response `{total: int, items: [{jibun_addr: str, pnu: str}]}`; no `road_addr`.
- Ruff line length 100, rules E/F/I. Tests flat in `tests/`, fixtures in `tests/fixtures/` (already saved: `vworld_search_ok.json`, `vworld_search_not_found.json`).

## Review Focus

- Keyword with surrounding spaces (`"  청평리 161  "`) → accepted and sent trimmed (`query == "청평리 161"`). (Task 2)
- Non-integer page (`page=abc`) → 422, VWorld not called. (Task 2)
- OK response whose `record.total` is a string (`"29"`) → `total == 29` as int. (Task 1)
- OK response with an empty `result.items` list → `(total, [])`, no crash. (Task 1)
- Hanja or Latin keyword (`淸平里`, `cheongpyeong`) → 422 (outside the whitelist), not 502. (Task 2)

---

### Task 1: VWorld search client and config

**Files:**
- Create: `app/farm/infrastructure/integrations/vworld.py`
- Modify: `app/core/config.py`, `tests/conftest.py`, `.env.example`
- Test: `tests/test_vworld_client.py`

**Interfaces:**
- Produces: `@dataclass(frozen=True) VworldLot(pnu: str, jibun_addr: str)`; `search_parcels(keyword: str, page: int, *, client: httpx2.Client | None = None) -> tuple[int, list[VworldLot]]`; `settings.vworld_api_key: str`.

- [ ] **Step 1: Write failing tests** (handler returns fixture text unless noted)

```python
def test_sends_search_params():        # params == {service: search, request: search, version: 2.0, type: address,
                                       #  category: parcel, crs: epsg:5179, format: json, size: 10, page: 2,
                                       #  query: "청평리 161", key: settings.vworld_api_key}
def test_ok_maps_total_and_lots():     # vworld_search_ok.json → total == 29, len == 10,
                                       # lots[0] == VworldLot("5111038022101610001", "강원특별자치도 춘천시 북산면 청평리 161-1")
def test_ok_with_no_items():           # {"response": {"status": "OK", "record": {"total": "0"}, "result": {"items": []}}} → (0, [])
def test_not_found_is_empty():         # vworld_search_not_found.json → (0, [])
def test_error_status_maps_to_code():  # 200 + {"response": {"status": "ERROR", "error": {"code": "INVALID_KEY"}}}
                                       # → 502, details == {"source": "vworld", "upstream_code": "INVALID_KEY"}
def test_html_400_maps_to_upstream_error():   # 400 + "<!DOCTYPE html>…" → details == {"source": "vworld"}
def test_item_without_id_raises():            # OK item missing "id" → details == {"source": "vworld"}
@pytest.mark.parametrize("error", [httpx2.ReadTimeout, httpx2.ConnectError])
def test_network_errors_map_to_upstream_error(error):   # → {"source": "vworld"}
```

- [ ] **Step 2:** `pytest tests/test_vworld_client.py -q` → FAIL (import error)
- [ ] **Step 3:** Add `vworld_api_key: str` to `Settings`; `os.environ.setdefault("VWORLD_API_KEY", "test-vworld-key")` in conftest; `VWORLD_API_KEY=` with a comment line in `.env.example`. Implement `search_parcels` following `farmmap.parcels_by_pnu` (default client `httpx2.Client(timeout=5)`, `httpx2.HTTPError` → 502). Read the body as JSON regardless of HTTP status; JSON decode failure, missing `response`, or `KeyError`/`TypeError` on an OK item → 502 `{"source": "vworld"}`.
- [ ] **Step 4:** `pytest -q` → all PASS; `ruff check .` clean
- [ ] **Step 5:** Commit `Add VWorld lot search client`

### Task 2: GET /addresses/search

**Files:**
- Modify: `app/farm/application/field_service.py`, `app/farm/presentation/schemas.py`, `app/farm/presentation/router.py`
- Test: `tests/test_address_search_api.py`

**Interfaces:**
- Consumes: `vworld.search_parcels` (call as module attribute so tests monkeypatch `app.farm.infrastructure.integrations.vworld.search_parcels`).
- Produces: `search_addresses(keyword: str, page: int) -> dict` (`{"total": int, "items": [{"jibun_addr", "pnu"}]}`); schemas `AddressItem(jibun_addr: str, pnu: str)`, `AddressSearchResult(total: int, items: list[AddressItem])`; `Keyword = Annotated[str, AfterValidator(check_keyword)]` where `check_keyword(value: str) -> str` returns the trimmed keyword or raises `ValueError`.

- [ ] **Step 1: Write failing tests** (stub records calls and returns `(29, [VworldLot("4182032521101610003", "경기도 가평군 청평면 청평리 161-3")])`)

```python
def test_returns_spec_shape():          # 200, body == {"total": 29, "items": [{"jibun_addr": "경기도 가평군 청평면 청평리 161-3",
                                        #  "pnu": "4182032521101610003"}]}; stub called with ("청평리 161-3", 1)
def test_keyword_is_trimmed():          # keyword="  청평리 161  " → stub called with ("청평리 161", 1)
def test_page_is_passed():              # page=3 → stub called with (…, 3)
@pytest.mark.parametrize("keyword", ["청", "가" * 81, "   ", "161-3", "청평리'", "청평리 <b>", "청평리%",
                                     "淸平里", "cheongpyeong 161"])
def test_invalid_keyword_is_422(keyword):     # 422, error.code == "VALIDATION_ERROR", stub not called
@pytest.mark.parametrize("page", ["0", "1001", "abc"])
def test_invalid_page_is_422(page):           # 422, stub not called
def test_missing_keyword_is_422():            # 422
def test_upstream_error_is_502():             # stub raises AppError 502 {"source": "vworld"} → 502, same details
```

- [ ] **Step 2:** `pytest tests/test_address_search_api.py -q` → FAIL (404)
- [ ] **Step 3:** Implement `check_keyword` and the schemas in `schemas.py`; `search_addresses` in `field_service.py`; route `GET /addresses/search` with `keyword: Annotated[Keyword, Query()]`, `page: Annotated[int, Query(ge=1, le=1000)] = 1`, `response_model=AddressSearchResult`, no auth.
- [ ] **Step 4:** `pytest -q` → all PASS; `ruff check .` clean
- [ ] **Step 5:** Manual: run uvicorn on a spare port, `GET /addresses/search?keyword=청평리 161-3` → `{"total": 1, "items": [{"jibun_addr": "경기도 가평군 청평면 청평리 161-3", "pnu": "4182032521101610003"}]}`; stop only that server process.
- [ ] **Step 6:** Commit `Add GET /addresses/search with VWorld`

### Task 3: Docs

**Files:**
- Modify: `docs/dev/팜가디언_API_명세.md` (§1 error table, §4 `GET /addresses/search`, §10 table), `docs/dev/팜가디언_아키텍처.md` (§4 layout, §8 table + juso section → VWorld search section, §9 settings)

- [ ] **Step 1:** Edit per the design's "Docs to update" list. The new §8 section states: call + params, response fields (`record.total` string, `id` = PNU, `address.parcel`), status handling table, firewall HTML 400 on `'`/`<>`, keyword whitelist, live findings (juso misses farmland; 30/30 PNU matched), Jeonnam-Gwangju limitation → issue #7. Keep the existing Korean style of each doc.
- [ ] **Step 2:** `grep -n -E "juso|road_addr|JUSO|pnu\.py|assemble_pnu" docs/dev/팜가디언_API_명세.md docs/dev/팜가디언_아키텍처.md` → only intentional historical mentions remain (e.g. "도로명주소 검색은 농지를 못 찾아 브이월드로 바꿨다").
- [ ] **Step 3:** Commit `Replace juso with VWorld search in API spec and architecture`
