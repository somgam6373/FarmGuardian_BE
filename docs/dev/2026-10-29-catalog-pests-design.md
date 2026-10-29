# Pest endpoints — BE-36 (design)

- Date: 2026-10-29
- Owner: Junhyeok (catalog context)
- Status: draft, waiting for approval
- Basis: **`팜가디언_API_명세.md` (the frame, unchanged)** §2 (`PestCard`), §6 (`GET /crops/{id}/symptom-parts`, `GET /pests/candidates`, `GET /pests`); `2026-10-29-catalog-pesticides-design.md` (the catalog read service this extends); `2026-10-29-static-catalog-design.md`

## The API spec is the frame

`팜가디언_API_명세.md` does not change and nothing here edits it.

```
PestCard {id: int, name: string, kind: "병"|"해충"|null, photo_url: string|null, photo_source: string|null,
          description: string|null, occurrence: string|null, occurrence_source: string|null,
          vectors: [{id, name, guide, source}]}
```

- `GET /crops/{id}/symptom-parts` → `[string]`: the symptom parts that have pests for the crop (a subset of 덩이, 뿌리, 잎, 줄기, 벌레, 열매); 404 for an unknown crop.
- `GET /pests/candidates?crop_id=&part=` → `[PestCard]` by name; a pest with several parts appears when any one matches; 404 for an unknown crop, 422 for a wrong `part`.
- `GET /pests?crop_id=&q=` → `[PestCard]`: pests **registered** for the crop, by name, pests without a 도감 entry included, no paging; `q` = optional partial name match; 404 for an unknown crop.
- All three need `X-User-Id` (spec §1). Errors use the common format.

## Intent

The pest side of the judgment flow: the user finds a pest by symptom part or by name, sees its card, then goes on to the drug list (BE-37) and the judgment.

## Goals

- Add pest functions to `catalog/application/catalog_service.py`, the `PestCard` entity to `domain/entities.py`, and the three routes and schemas to `presentation/`.
- Build the cards from the static data: `pest.json`, `pest_photo.json`, `pest_season.json`, `virus_vector.json`.
- Tests: service tests over the real data (pinned counts and an independent oracle), API tests with the test database.

## Non-goals

- Spray records (BE-46/47), the judgment API (BE-45), `get_pesticide` and registration rows for judgment input (added there).
- Searching by `pest_alias.json` names, a single-pest detail endpoint, listing every photo of a pest.
- Any database table, `schema.sql` change, or change to existing endpoints.

## Data and numbers

| Crop | Pests | Registered (`GET /pests`) | With parts (candidates) | With occurrence | Viruses with vectors |
|---|---|---|---|---|---|
| 감자 | 31 | 25 | 26 | 8 | 0 |
| 배추 | 52 | 43 | 47 | 27 | 2 |
| 토마토 | 46 | 23 | 43 | 14 | 4 |

Parts per crop (candidates per part): 감자 덩이 13, 뿌리 3, 잎 11, 줄기 7, 벌레 12, 열매 1; 배추 잎 38, 뿌리 8, 줄기 16, 벌레 27; 토마토 뿌리 6, 잎 36, 줄기 26, 열매 22, 벌레 17. 13 pests have no 도감 (`has_doc` false, no `parts`); 38 pests have parts but no registered drug. 102 pests have photos (1–4 each, only 25 flagged `is_main`).

## Behaviour

**Pest card** (`pest_id` = card `id`; pests are per crop, so a card is always "this crop's" pest):
- `name`, `kind` (`disease` → 병, `insect` → 해충), `description` = `symptom` (null when empty).
- **Photo:** the pest's `is_main` photo, else its first photo (smallest `photo_id`); `photo_url` = its `url`, `photo_source` = `pest.photo_crop` (「토마토」, 「양배추(대체)」, 「옥수수(보충)」…). No photo → both null.
- **Occurrence:** from `pest_season.json`; when a pest has an `ncpms` row it is used, otherwise its `pdf` row. `occurrence_source` = 「NCPMS 설명」 / 「PDF 경보」. `occurrence` = the months, then ` — ` and the basis when there is one:
  - months: sorted, runs of two or more consecutive months as `a~b`, joined with `, `, ending in `월` (`[4,5,6,7]` → `4~7월`, `[6,8,9]` → `6, 8~9월`);
  - basis: `ncpms` → its `evidence` sentence; `pdf` → `region`, `culti`, `grade` that exist, joined with ` · ` (`대관령 · 고랭지, 씨감자 · 예보`).
  No row → both null.
- **Vectors:** for a virus pest, one entry per `virus_vector.json` row with a vector pest: `id` = vector pest id, `name` = its name, `guide` = `guide_text`, `source` = `evidence`; ordered by name. A row without a vector pest gives nothing; no rows → `[]`.

**Endpoints:**
- `symptom-parts`: the crop's distinct `parts` values in the fixed order 덩이, 뿌리, 잎, 줄기, 벌레, 열매.
- `candidates`: pests of the crop whose `parts` contain `part`, **whether or not a drug is registered for them**; `part` not in that crop's symptom-part list → 422 `VALIDATION_ERROR` (`loc` `["query", "part"]`).
- `pests`: pests of the crop with at least one registration row (`pesticide_use`); `q` trimmed, blank means no filter, otherwise case-insensitive substring of the name.
- Order everywhere: name ascending.

## Calls I made (please check)

1. **Candidates are not limited to registered pests** (spec §6 names that limit only for `GET /pests`). A candidate without a registered drug leads to an empty `GET /pesticides?pest_id=` and a judgment `BLOCKED` at ①; the frontend can say 「등록된 약이 없습니다」. This makes 토마토 offer 43 candidates against 23 listed pests.
2. A `part` that is valid in general but absent for the crop (e.g. 덩이 for 토마토) is a 422, because the spec says it must be one of the values from `symptom-parts`.
3. **Representative photo:** `is_main`, else the first photo; the data flags only 25 pests as main.
4. **Occurrence format** (the spec leaves it open): month ranges plus a basis text as above; `ncpms` is preferred over `pdf` when both exist (2 pests).
5. `q` matches names only, not `pest_alias.json`.
6. Vectors are ordered by name; the one virus row without a vector pest (`virus_pest_id` 64) yields `[]`.
7. The entity `PestCard` and the functions `list_symptom_parts`, `list_candidates`, `list_pests` sit next to the pesticide ones in the existing service; the router file gains three routes.

## Tests

- **Service (real data):** symptom parts per crop in order (6 / 4 / 5 values); candidate counts per crop and part exactly as in the table; `GET /pests` counts 25 / 43 / 23 and that every returned pest has a registration row (independent oracle from `pesticide_use`); registered pests without 도감 appear; candidates of 토마토 include pests without registrations (43 vs 23); a multi-part pest appears under each of its parts; names sorted; `q` cases (substring, trimmed, blank, no match, uppercase ASCII).
  Cards: kind mapping; photo rule (a pest whose first photo is not main but another is → the main one; a pest without `is_main` → the first; no photo → null); occurrence samples (an `ncpms` sentence pest, a `pdf` pest with region and culti, a two-row pest uses `ncpms`, no row → null) and the month formatter on several lists; vectors (a virus with three vectors, the one without a vector pest → `[]`, a non-virus → `[]`).
  Errors: unknown crop (all three), a `part` outside the crop's list.
- **API (test database):** 401 without the header on all three; shapes (`PestCard` has exactly the 9 keys, `vectors` items `id, name, guide, source`); 404 and 422 bodies in the common format; missing `crop_id` / `part` → 422.

## Left to the builder

Helper names, how the photo/season/vector indexes are cached.

## Open questions (not blocking)

- The occurrence text format and the representative-photo rule should be shown to the frontend once; both are server-side and can change without touching the spec.
