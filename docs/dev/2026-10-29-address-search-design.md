# GET /addresses/search — VWorld lot search (design)

- Date: 2026-10-29
- Owner: Hyebin (farm context), issue #3
- Status: approved in chat (2026-10-29)
- Basis: `팜가디언_API_명세.md` §1, §4; `팜가디언_아키텍처.md` §8, §9. Team agreed (Junhyeok, frontend) to replace the juso search with VWorld search on 2026-10-29.

## Intent

Field registration starts with the user typing their lot (e.g. `청평리 161-3`) and picking it to get a PNU,
which `GET /parcels` (#2) turns into Farmmap parcels.

The juso (도로명주소) search API returns only lots with buildings, so farmland is not found
(live check 2026-10-29: `청평리 161-3`, a 밭, → 0 results; juso found only `161-7`, `161-15` which have buildings).
VWorld search (`req/search`, `type=address`, `category=parcel`) finds every lot, and each result's `id`
is the 19-digit PNU (30/30 sampled results matched VWorld's geocoder).

## Goals

- `GET /addresses/search?keyword&page` returns matching lots with their PNU, 10 per page.
- Keywords that VWorld's firewall rejects never reach VWorld.
- API spec and architecture doc describe VWorld search instead of juso + PNU assembly.

## Non-goals

- `juso.py`, `pnu.py`, `JUSO_CONFM_KEY` (dropped).
- Road-name (도로명) address input: `category=parcel` does not match them; farmland has none.
- Region filter or ranking. Same village names from several regions all come back; the user picks
  from the full address (team decision).
- Reverse geocoding (`vworld.reverse_geocode`, arch §8) — separate, still undecided.
- Jeonnam-Gwangju Farmmap code mismatch (#7).

## Behaviour

Request: `GET /addresses/search?keyword=&page=` — no `X-User-Id` required.

Validation (422 `VALIDATION_ERROR`, before calling VWorld):
- `keyword`: required, 2–80 characters after trimming, only Hangul syllables, digits, spaces and `-`,
  and at least one Hangul syllable.
  (Builder's call: a whitelist. Live calls showed `'` and `<>` get an HTML 400 from VWorld's firewall;
  the allowed set covers lot input such as `가평 청평리 산1-1`. Digits-only stays rejected as in the
  current spec: `161` alone matched 50,387 lots nationwide, useless without a village name.)
- `page`: integer 1–1000, default 1 (VWorld's limit; outside it VWorld answers `INVALID_RANGE`).

Upstream call: `GET https://api.vworld.kr/req/search` with `service=search`, `request=search`,
`version=2.0`, `type=address`, `category=parcel`, `crs=epsg:5179`, `format=json`, `size=10`, `page`,
`query=keyword`, `key=VWORLD_API_KEY`. `httpx2` sync client, timeout 5 s, no retry. The URL carries the
key; the `httpx2` logger is already kept below INFO (`farmmap.py`).

Response: `200 {total: int, items: [{jibun_addr: string, pnu: string}]}`
- `total` = `response.record.total` (a string in VWorld's JSON) as int.
- `jibun_addr` = `item.address.parcel`, `pnu` = `item.id`. Order as VWorld returns it.

Upstream result handling (live-checked 2026-10-29):

| VWorld returns | Our response |
|---|---|
| `response.status == "OK"` | 200, mapped items |
| `"NOT_FOUND"` (no match, or page past the last) | 200, `{total: 0, items: []}` |
| `"ERROR"` (`INVALID_KEY`, `PARAM_REQUIRED`, `INVALID_RANGE`, …; note: HTTP 200) | 502 `UPSTREAM_ERROR`, `{source: "vworld", upstream_code: error.code}` |
| non-JSON body (firewall HTML 400 etc.), timeout, connection error, OK item without `id`/`address.parcel` | 502, `{source: "vworld"}` |

## Code layout

- `app/farm/infrastructure/integrations/vworld.py`: `search_parcels(keyword, page, *, client=None)` →
  `(total, list[VworldLot])`; `VworldLot(pnu, jibun_addr)`.
- `app/farm/application/field_service.py`: `search_addresses(keyword, page)` → `{total, items}`.
- `app/farm/presentation/router.py`, `schemas.py`: `GET /addresses/search`, `AddressSearchResult`.
- `app/core/config.py`: required `vworld_api_key` (`VWORLD_API_KEY`); `.env.example`, `tests/conftest.py`.

## Docs to update (same PR)

- API spec §1 error table: `VALIDATION_ERROR` loses the juso `details` case; `UPSTREAM_ERROR.source`
  becomes `"vworld"|"farmmap"|"kma"`.
- API spec §4 `GET /addresses/search`: response without `road_addr`, new validation rule, page range.
- API spec §10 external API table: `/addresses/search` → VWorld search.
- Architecture §4 layout (drop `juso.py`, `pnu.py`), §8 table + replace the juso section with a VWorld
  search section (call, response, errors, live findings above, Jeonnam-Gwangju note pointing to #7),
  §9 settings (drop `JUSO_CONFM_KEY`).

## Tests (no network)

- Client (`httpx2.MockTransport`): sends the params above; OK → total + lots; NOT_FOUND → `(0, [])`;
  ERROR → 502 + `upstream_code`; HTML 400 → 502; timeout → 502; OK item missing `id` → 502.
  Fixtures (live, saved 2026-10-29): `tests/fixtures/vworld_search_ok.json` (`청평리 161`, page 1:
  `record.total` `"29"` as a string, 10 items, first `5111038022101610001` /
  `강원특별자치도 춘천시 북산면 청평리 161-1`) and `vworld_search_not_found.json` (`청평리 9999`).
- API (client monkeypatched): valid → spec shape; keyword with `'`, `<`, `%`, 1 char, 81 chars,
  whitespace only, digits only (`161-3`) → 422 and VWorld not called; page 0 / 1001 → 422; missing keyword → 422; upstream
  error → 502.

## Left to the builder

Internal names beyond those above, error messages (Korean, like the existing ones).
