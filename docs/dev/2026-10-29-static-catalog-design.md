# Static catalog data — JSON in the repo (design)

- Date: 2026-10-29
- Owner: Junhyeok (catalog context)
- Status: draft, waiting for approval
- Basis: `팜가디언_판정_규칙.md` §1 (③ 집계 단위), §10-1; `팜가디언_아키텍처.md` §4 (layout), §5 (schema), §8 (데이터 적재); the JSON set delivered through Notion ("DB 전달서"), copied to `C:\Users\USER\Desktop\팜가디언 json` on 2026-10-29

## Intent

Pesticide, pest and crop reference data never changes while the app runs, and one person edits it a few times a month at most. Instead of loading it into PostgreSQL (the Excel → JSON → DB pipeline of arch §8), the JSON files delivered by the data owner are committed to the repo and read into memory. This removes the loader, the catalog tables and the foreign keys into them, and lets the judgment tests run on the real data without a database.

## Decisions made with Junhyeok

- Reference data is static JSON files inside the repo, read into process memory. No S3 or other bucket (about 2.6 MB, no access keys, tests stay offline).
- ③ count is summed by item name (`item_name`), as in the judgment rules. Summing by ingredient (§10-1) stays an open question; the ingredient files are kept so it can be switched later.

## Goals

- The 12 reference files are in the repo, byte for byte as delivered, and readable through one function.
- Tests pin what the data must look like (row counts, unique ids, every reference resolves) so a bad re-delivery fails in CI instead of in a judgment.
- `schema.sql`, the architecture doc and the role doc say the same thing as the code: no catalog tables in the database.

## Non-goals

- Mapping the JSON rows to the judgment input types (`registrations`, `usage_type` …). That belongs to the BE-38/39 design.
- Any API endpoint (`/crops`, `/pests`, `/pesticides` …), search, or judgment code.
- `xlsx_to_json` (BE-31) and the DB loaders (BE-32 … 35): dropped, the data owner delivers JSON.
- The 4 test-seed files (`app_user`, `field`, `zone`, `spray_log`): uuid user ids, marked `is_test`. They are input for the demo seed (BE-48), not reference data.
- Editing the JSON content. Data fixes go back to the data owner.

## Data inventory (all UTF-8, no BOM, no secrets, e-mail or phone numbers)

| File | Rows | Role |
|---|---|---|
| `crop` | 3 | 감자 1, 배추 2, 토마토 3 (same ids and order as the `crop` seed in `schema.sql`) |
| `moa` | 70 | action groups: `kr_code`, `intl_code`, `is_multi_site` |
| `ingredient` | 216 | active ingredients, `moa_id` (5 without) |
| `pest` | 129 | one row per crop and pest (`crop_id`), `kind` = `disease` / `insect` |
| `pest_alias` | 16 | other names |
| `pest_photo` | 185 | photo URLs (external, NCPMS) |
| `pest_season` | 51 | occurrence months |
| `pesticide_use` | 4,133 | one row per registered use: `product` (= item name), `brand`, `company`, `moa_code`, `method`, `dilution`, `use_time`, `use_count` (raw text) |
| `safe_use_std` | 4,133 | 1:1 with `pesticide_use` by `use_id`: `phi_days`, `max_count`, `parse_status` (`ok` 3,531 / `stage` 554 / `no_std` 41 / `failed` 7), `note`, `base_date` |
| `use_ingredient` | 4,949 | `use_id` → `ingredient_id`, 1 or 2 per use |
| `rotation_rule` | 6 | ④ repeat rules |
| `virus_vector` | 12 | virus → vector pest, 1 without a vector |

`use_id` runs 1 … 4,133 without gaps. There are 652 distinct `product` values and 1,363 distinct (`product`, `brand`) pairs.

## Calls I made (please check)

1. **Location.** Files in `app/catalog/data/`, original names. The loader is `app/catalog/infrastructure/static_data.py` (arch §4 keeps file access in `infrastructure`).
2. **Loader API.** `load(name: str) -> list[dict]`: reads `<name>.json` from the data folder, cached with `functools.cache`, lazy (first call). Only the 12 names above are accepted, anything else raises `ValueError`. The returned objects are shared and must not be modified. No change to `app/main.py`.
3. **Pesticide identity.** The data has no pesticide table. A pesticide is a (`product`, `brand`) pair, `item_name = product` (this is the summing key of ③). Its id is the smallest `use_id` of the pair, so it stays the same as long as `use_id` values are never renumbered. Data updates must append new `use_id`s only; a test pins a few known (`use_id` → product, brand) pairs to catch a renumbered re-delivery.
4. **`crop` stays in the database** (3 rows, `zone.crop_id` foreign key). A DB test checks that `crop.json` and the table agree on id and name.
5. **`schema.sql`.** Drop the 9 catalog tables (`moa`, `pesticide`, `pest`, `pest_info`, `pest_photo`, `pest_symptom`, `pest_occurrence`, `pest_vector`, `registration`). `spray_log.pesticide_id`, `judgment.pest_id` and `judgment.pesticide_id` keep their columns but lose the foreign keys; they hold static ids. There are no migrations, so everyone recreates their dev and test database from `schema.sql` (the PR description says so).
6. **Documents.** Update arch §4 (tree: no `ingest/`), §5 (no catalog tables), §8 (「데이터 적재」 becomes 「정적 참고 데이터」) and the role doc rows for `catalog`. The BE backlog rows BE-31 … 35 become obsolete; the backlog is an Excel file the team edits, so I do not touch it.

## Data checks (table-based pytest, no database)

Row counts as in the inventory; ids unique per file; `safe_use_std` and `pesticide_use` have the same `use_id` set; every `use_ingredient` reference, `ingredient.moa_id`, `pesticide_use.pest_id`, `pest.crop_id`, `pest_season.pest_id`, `pest_photo.pest_id` resolves. Known gaps are pinned, not hidden, so a change shows up as a failing test: 5 ingredients without `moa_id`; `pesticide_use.moa_code` values that are not in `moa.kr_code` (compound codes such as `13+22b`; the test records the current set); 17 uses without `moa_code`; 1 `virus_vector` row without a vector pest.

## Left to the builder

Test file names and the exact pinned (`use_id`, product, brand) samples; whether `load` returns the list or a tuple of the same dicts; the helper that builds the pesticide list (call 3) can wait for its first user (BE-37 / BE-38).

## Open questions (not blocking)

- Summing by ingredient (§10-1) once the data owner confirms the legal basis.
- Whether the data owner's own SQL ("DB 전달서 4") and our judgment rules should be reconciled; they currently differ on the empty-history case (judgment rules §1 「이력 확인」).
