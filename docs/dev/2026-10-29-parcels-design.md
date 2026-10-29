# GET /parcels — Farmmap parcel lookup (design)

- Date: 2026-10-29
- Owner: Hyebin (farm context)
- Status: approved in chat (2026-10-29)
- Basis: `팜가디언_아키텍처.md` §4 (layout), §8 (Farmmap), §9 (common rules); `팜가디언_API_명세.md` §1, §2 (`Parcel`), §4 (`GET /parcels`)

## Intent

During field registration the user picks Farmmap parcels (`fmapInnb`) that overlap a lot (PNU).
This PR delivers `GET /parcels?pnu=` end to end: call Farmmap, parse its XML, return `[Parcel]`.
It is the first PR of the farm context and does not depend on the address-search decision
(the endpoint takes a PNU directly) or on the database.

## Goals

- `GET /parcels?pnu={19 digits}` returns every Farmmap parcel overlapping that lot, in the
  `Parcel` shape of the API spec.
- A pure parser `parse_farmmap_response(xml) -> list[FarmmapParcel]` tested against a saved real
  response.
- Upstream failures map to the common error format (`502 UPSTREAM_ERROR`, `details.source = "farmmap"`).

## Non-goals (later PRs)

- `parcel_by_id` (needed by `POST /fields`, PR 3).
- `used_by_field_id` lookup: always `null` until fields are stored (PR 3). No auth on this endpoint.
- Address search (PR 2), any DB access, caching, retries, parallel fetching.

## Behaviour

Request: `GET /parcels?pnu=` — no `X-User-Id` required. `pnu` must match `^\d{19}$`, else 422
`VALIDATION_ERROR` before calling Farmmap.

Upstream call: `GET http://apis.data.go.kr/B552895/getFarmmapService/getPnuBasedFarmmapInfo`
with `serviceKey`, `type=xml`, `pnuCode`. `httpx2` sync client, timeout 5 s, no retry.

Upstream result handling (arch §8, confirmed by live calls 2026-10-28/29):

| Farmmap returns | Our response |
|---|---|
| `response/header/resultCode` `0` or `00` | 200, parsed parcels |
| `resultCode` `3` (NODATA) | 200, `[]` |
| any other `resultCode` | 502, `details.upstream_code` = that code |
| gateway format `OpenAPI_ServiceResponse/cmmMsgHeader` (bad key etc., HTTP 403) | 502, `upstream_code` = `returnReasonCode` |
| timeout, connection error, non-XML body, other HTTP error without a parsable body | 502, no `upstream_code` |

- `<totalCount>` is ignored (live response had 2 items with `totalCount` 0). Parcels = `<item>` elements.
- The request URL contains the key: it must not be logged (silence the `httpx2` logger below WARNING).

Parsing each `<item>`:

| XML | `FarmmapParcel` field | Note |
|---|---|---|
| `fmapInnb` | `farmmap_id: str` | |
| `pnuLnmCd` | `pnu: str` | |
| `lnm` | `lnm: str` | e.g. `161-3전` |
| `intprNm` | `land_use: str` | 논·밭·과수·시설 |
| `vdptYr` | `vdpt_yr: int \| None` | live value is a date `2022-04-01`; take the first 4 chars. Empty/invalid → `None` |
| `fmapBdcrd` GML `MultiPolygon` (EPSG:5179) | `polygons` | list of polygons; each polygon = outer ring + inner rings (holes); ring = list of `(x, y)` floats from `gml:coordinates` (`x,y x,y …`) |

Holes (`innerBoundaryIs`) are parsed even though no live sample has one yet.

A `resultCode 0` response with a malformed `<item>` (missing `fmapInnb`/`pnuLnmCd`/`fmapBdcrd`,
unparsable coordinates) fails the whole request with 502 and no `upstream_code` (builder's call:
fail loudly rather than silently drop a parcel).

Key: `FARMMAP_API_KEY` holds the 64-char hex key, identical in encoded and decoded form, so it is
passed through `httpx2` `params=` (verified by live calls on 2026-10-29).

Response mapping (`Parcel`, API spec §2):

- `geometry`: GeoJSON `MultiPolygon`, coordinates rounded to 1 decimal.
- `bbox` is not part of `Parcel`.
- `area_m2`: computed in Python with the shoelace formula on the unrounded coordinates
  (outer rings minus holes), rounded to 1 decimal. EPSG:5179 is metric, so the result is m².
  Lives in `farm/domain` so the split work (PR 4) can reuse it.
- `matches_query`: `parcel.pnu == requested pnu`.
- `used_by_field_id`: `null`.
- Order: as Farmmap returns them.

## Code layout (arch §4)

- `app/farm/infrastructure/integrations/farmmap.py`: `parcels_by_pnu(pnu)` (HTTP) and
  `parse_farmmap_response(xml)` (pure), `FarmmapParcel` dataclass, upstream error.
- `app/farm/domain/geometry.py`: polygon area (pure).
- `app/farm/application/field_service.py`: `find_parcels(pnu)` → builds the response values.
- `app/farm/presentation/schemas.py`, `router.py`: `Parcel` schema and `GET /parcels`; router
  included in `app/main.py`.
- `app/core/config.py`: add required `farmmap_api_key` (`FARMMAP_API_KEY`); `.env.example` gets
  the name without a value; `tests/conftest.py` sets a dummy value.
- `requirements.txt`: add `httpx2` (runtime dependency). The project uses `httpx2`, the successor
  package that Starlette's `TestClient` imports; plain `httpx` is not installed.

Upstream failures raise `AppError("UPSTREAM_ERROR", 502, …, {"source": "farmmap", "upstream_code"?})`
from `app/core/errors.py`.

## Tests (no network)

- Parser: live response for PNU `4182032521101610003` fetched 2026-10-29 (2 items: `161-3전` 밭,
  `160-7답` 논), committed as `tests/fixtures/farmmap_pnu_4182032521101610003.xml` (public data)
  → 2 parcels with expected fields. The test pins this file; a later Farmmap update does not
  change it; a hand-written XML with a hole; `vdptYr` empty.
- Area: 10 m × 10 m square = 100; square with a 2 m × 2 m hole = 96.
- Client (`httpx2.MockTransport`): code `0`, `00`, `3` → `[]`, other code → 502 + code, gateway
  403 → 502 + `returnReasonCode`, timeout → 502.
- API (`TestClient`, client monkeypatched): bad PNU → 422 in the common error format; valid PNU →
  spec-shaped JSON with `matches_query` true/false and `used_by_field_id` null; upstream error → 502.

## Left to the builder

Internal names beyond those above, file split inside tests, exact error messages (Korean,
matching existing ones in `app/core/errors.py`).
