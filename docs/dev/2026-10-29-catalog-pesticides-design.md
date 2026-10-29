# Catalog read service, `GET /crops` and `GET /pesticides` — BE-37 (design)

- Date: 2026-10-29
- Owner: Junhyeok (catalog context)
- Status: draft, waiting for approval
- Basis: **`팜가디언_API_명세.md` (the frame, unchanged)** §1, §2 (`Moa`, `Crop`, `Pesticide`), §4 (`GET /crops`), §6 (`GET /pesticides`); `2026-10-29-static-catalog-design.md`; `팜가디언_판정_규칙.md` §3 (사용 유형), §7 (sorting)

## The API spec is the frame

`팜가디언_API_명세.md` does not change and nothing here edits it.

- `GET /crops` → `[Crop {id, name}]` (감자, 배추, 토마토), authenticated (`X-User-Id`; only signup, login, address search and parcels are open).
- `GET /pesticides?crop_id=&pest_id=` → `[Pesticide + {at_planting_only}]` where `Pesticide {id: int, name: string, item_name: string, moa: Moa|null}`, `name` = brand (상표명), `item_name` = item (품목명), `Moa {label_kr, system, code}`. Sorted 작용기작 → 품목명 → 상표명, no paging, errors 404 / 422 in the common error format.
- `at_planting_only`: true when every registration row of the drug for the crop (and the pest, if given) is a 「심을 때」 use; such a drug gets ② `NEEDS_CHECK` in the judgment.

## Intent

First read service of the catalog context. It turns the static JSON into the objects the API describes and fixes the drug identity that spray records and judgments will store. The frontend can then fill the crop and drug pickers; BE-36 (pests), BE-46/47 (spray records) and BE-45 (judgment API) build on it.

## Goals

- `catalog/domain/entities.py`: frozen dataclasses `Crop`, `Moa`, `Pesticide` (the spec's fields plus `at_planting_only` carried by the list result).
- `catalog/application/catalog_service.py`: `list_crops()` and `list_pesticides(crop_id, pest_id)` over the static data; the drug index is built once and cached.
- `catalog/presentation/router.py` + `schemas.py`: `GET /crops`, `GET /pesticides`, registered in `app/main.py`, both behind `current_user`.
- Tests: service tests without a database over the real data, API tests with the test database.

## Non-goals (other tasks)

- Pest endpoints and pest cards (BE-36); `get_pesticide(id)` for spray validation (BE-46); the conversion of rows into judgment inputs and the candidate pool for alternatives (BE-45). Each adds its function to the service when it needs it.
- Any database table for catalog data; any change to `schema.sql`.
- Paging, search or filtering beyond `crop_id` / `pest_id`.

## Behaviour

- **Crops:** from `crop.json`, ordered by `id`. (The `crop` table has the same ids and names; a test already pins that.)
- **Drug identity (static-catalog design):** a drug is a (`product`, `brand`) pair; `id` = the smallest `use_id` of the pair over all crops, `item_name` = `product`, `name` = `brand`. 1,363 drugs; each has exactly one `moa_code`.
- **`moa`:** `moa_code` None → `moa` null. A single code is looked up in `moa.json`: `label_kr` = the code, `system` / `code` = `intl_code` split at the first space (`FRAC 21` → `FRAC`, `21`; `FRAC M 01~M 13` → `FRAC`, `M 01~M 13`); no `intl_code` → both null. A compound code (`카+가1`, 192 of the 254 codes in use) → `label_kr` = the code, `system` and `code` null (judgment rules §4 ④: an unknown `system` means 「그 밖의 계열」).
- **List:** drugs having at least one registration row on a pest of the crop; with `pest_id`, only rows of that pest. Each drug once. `at_planting_only` = all those rows have `parse_status == "stage"`.
- **Order:** `moa.label_kr` ascending with drugs without `moa` last, then `item_name`, then `name`.
- **Errors:** unknown `crop_id` → 404 `NOT_FOUND`; unknown `pest_id`, or a pest that belongs to another crop → 404 `NOT_FOUND` (pests are per crop in the data); missing or non-integer query values → 422 `VALIDATION_ERROR`; no `X-User-Id` → 401.

Real sizes: 감자 508 drugs (103 at-planting-only, 3 without `moa`), 배추 1,008 (171, 4), 토마토 515 (57, 5).

## Calls I made (please check)

1. Crops are read from `crop.json`, not the database; no query is needed and the table is kept equal by a test. Authentication still uses the database through `current_user`.
2. `moa.system` / `moa.code` come from splitting `intl_code` at the first space. Odd forms (`FRAC 11 / 11A`, `FRAC BM 01`) keep the rest as `code`.
3. A compound `moa_code` gives `system` / `code` null even though its parts are known, as in the judgment rules.
4. Sorting by `moa.label_kr` (the Korean code, as in judgment rules §7), drugs without `moa` last. The spec does not define the order inside 「작용기작」.
5. A `pest_id` of another crop is a 404, not an empty list.
6. The service raises `AppError("NOT_FOUND", 404, …)` like `field_service` does for its errors.
7. The layout follows arch §4: entities in `domain`, functions in `application`, router and response schemas in `presentation`.

## Tests

- **Service (no database, real data):** three crops in order; drug counts 508 / 1,008 / 515; ids unique; id rule (`아미설브롬 입상수화제` / `엑사이도` has id 1); `at_planting_only` counts 103 / 171 / 57 and `moa` null counts 3 / 4 / 5; the sort order holds for every list; `moa` samples (`가1` → FRAC 4, `카` → `M 01~M 13`, a compound code, no `intl_code`); `pest_id` narrows the list and keeps ids; unknown crop, unknown pest and a pest of another crop raise 404.
- **API (test database):** 401 without the header for both endpoints; `GET /crops` shape; `GET /pesticides?crop_id=2` returns 1,008 items whose keys are exactly `id, name, item_name, moa, at_planting_only`; `moa` is null or `{label_kr, system, code}`; 404 and 422 bodies use the common error format.

## Left to the builder

File and helper names, how the cached index is stored.

## Open questions (not blocking)

- Whether the frontend wants the drugs grouped by action group on the server; the spec asks for a flat sorted list, so none here.
