# Farmmap `parcel_by_id` (design)

- Date: 2026-10-29
- Owner: Hyebin (farm context), part of issue #4
- Status: approved in chat (2026-10-29)
- Basis: `팜가디언_아키텍처.md` §7 「밭 생성」, §8 「팜맵 조회」; `팜가디언_API_명세.md` §3 `POST /auth/signup`, §5 `POST /fields`

## Intent

When a user registers a field (`POST /auth/signup` or `POST /fields`), the frontend sends only the
chosen Farmmap parcel ids (`parcel_farmmap_ids`, 1–20). The server never trusts client geometry
(arch §7), so it re-fetches each parcel's shape from Farmmap by id. This PR adds that lookup;
field storage and the parallel fetch (≤ 8 at a time) come with `POST /fields` (#4).

## Goal

`parcel_by_id(farmmap_id: str, *, client: httpx2.Client | None = None) -> FarmmapParcel | None`
in `app/farm/infrastructure/integrations/farmmap.py`.

- Upstream: `GET http://apis.data.go.kr/B552895/getFarmmapService/getIdBasedFarmmapInfo` with
  `serviceKey`, `type=xml`, `id`. Same timeout (5 s), no retry, same key-out-of-logs rule as
  `parcels_by_pnu`.
- Parsing: the response has the same format as the PNU lookup (live check 2026-10-29), so it reuses
  `parse_farmmap_response`.
- Result: the parcel whose `farmmap_id` equals the requested id, or `None` when there is none
  (`resultCode 3`: unknown id, malformed id such as `abc` — both live-checked). If Farmmap returns
  other parcels but not the requested one, also `None` (builder's call: never hand back a different
  parcel's shape).
- Errors: exactly as `parcels_by_pnu` — network error, gateway error, other codes, malformed body
  → `AppError` 502 `UPSTREAM_ERROR`, `source: "farmmap"`.

## Non-goals

- `POST /fields`, `POST /auth/signup`, parallel fetching, DB (#4, and Junhyeok's signup).
- Mapping `None` to 422 `not_found` — the caller does that (API spec §3: `errors[].loc =
  ["body", "parcel_farmmap_ids", index]`, `type: "not_found"`).

## Code

- Extract the shared request part of `parcels_by_pnu` into one private helper
  `_fetch(url, params, client) -> list[FarmmapParcel]` (HTTP call + `httpx2.HTTPError` → 502 +
  parse) and use it from both functions. Behaviour of `parcels_by_pnu` unchanged (its tests stay).
- New constant `ID_URL` next to `PNU_URL`.

## Tests (no network)

- Fixture: live response for id `418203252100637` saved 2026-10-29 as
  `tests/fixtures/farmmap_id_418203252100637.xml` (1 item, `161-3전`, 밭).
- Sends `serviceKey`, `type=xml`, `id`, path ends with `/getIdBasedFarmmapInfo`.
- Fixture → parcel with `farmmap_id == "418203252100637"`, `lnm == "161-3전"`.
- `resultCode 3` → `None`.
- Response with a different parcel only → `None`.
- Gateway 403 → 502 with `upstream_code "30"`; timeout → 502.
- Existing `parcels_by_pnu` tests still pass.
