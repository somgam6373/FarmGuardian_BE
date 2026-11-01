# Inventory (창고) — `POST|GET|DELETE /inventory` (design)

- Date: 2026-11-01
- Owner: Junhyeok (new `inventory` context)
- Status: **approved** (2026-11-01, including creating the table in the dev and test databases)
- Basis: the frontend's message of 2026-11-01 and `frontend/docs/api-wanted.md` (2026-10-30, §1 crops, §2 inventory);
  `팜가디언_API_명세.md` §1 (common rules), §3 `DELETE /me`; `팜가디언_아키텍처.md` §4, §5, §9;
  the spray API (`app/spraying`) as the pattern for catalog-id validation and duplicate handling.
- Rule applied: what the frontend's request leaves open, the team decides (`【결정】`), as with the OCR endpoint.

## Intent

A drug judged 「가능」 is useless today if the farmer does not have it. The frontend keeps a 창고 (the
drugs the user owns): the verdict screen has an 「넣기」 button, and the map home and drug list show an
in-stock badge and sort in-stock drugs first among equal verdicts. Today this lives in browser memory
(`mock.ts` `INVENTORY`, `AppState.toggleInventory`). It must survive reloads and devices, so the server
stores it.

## What the frontend needs, and what it does not

- The frontend only asks `inventory.includes(drug.id)` on drugs it already holds (from `GET /pesticides`,
  judgment alternatives, OCR candidates). So `GET /inventory` returns ids only; **no drug-by-id lookup
  API is needed.**
- `GET /crops` already exists and serves the crop picker (감자 1, 배추 2, 토마토 3). Nothing to build.

## Goals

1. Three endpoints on a new `inventory` context, all behind `X-User-Id`; each user sees only their own.
2. The stored id is the catalog drug id (`pesticide.id`), so it matches every other API.
3. Withdrawal (`DELETE /me`) removes the user's inventory.

## Non-goals

- Using the inventory in judgments or alternatives, quantities, expiry, or purchase history.
- A drug-by-id lookup, a search parameter on `GET /crops` (`api-wanted.md` shows `?q=`; there are three
  crops, the parameter is ignored and the full list returned; add a one-line filter if asked).
- Region statistics and OCR match reasons: see "Found while reading" below, not part of this work.

## Contract (`【결정】` marks my calls where the request is silent)

| API | Request | Response |
|---|---|---|
| `POST /inventory` | `{drug_id: int}` | `201 {drug_id}` when newly added, `200 {drug_id}` when it was already there (retry-safe, no error) |
| `GET /inventory` | none | `200 [int]`, ids in the order they were added (oldest first) 【결정】 |
| `DELETE /inventory/{drug_id}` | none | `204` |

- Field name `drug_id` follows the frontend's request; it is the same number as `pesticide_id` /
  `pesticide.id` elsewhere 【결정】.
- Errors: `401` (common). `POST`: `422 VALIDATION_ERROR` with `loc ["body","drug_id"]` when the id is not
  in the catalog (same type and message style as the spray API's unknown drug). `DELETE`: `404 NOT_FOUND`
  when the id is not in this user's inventory, **including ids outside the catalog, answered before any
  database access** (a huge id would overflow the `int` column otherwise) 【결정】. A non-integer path
  value is the usual `422`.

## Storage (`schema.sql`, additive)

```sql
CREATE TABLE inventory (
    user_id      bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    pesticide_id int    NOT NULL,                       -- 정적 데이터의 약제 id (FK 없음)
    created_at   timestamptz NOT NULL DEFAULT clock_timestamp(),   -- now()는 트랜잭션 안에서 같은 값이라 담은 순서를 못 가린다
    PRIMARY KEY (user_id, pesticide_id)
);
```

`clock_timestamp()` instead of `now()`: `now()` is the transaction's start time, so rows added in one
transaction (every test, and a client that batches calls) would tie and lose their order 【결정】.

The primary key makes a repeated add a no-op (`INSERT … ON CONFLICT DO NOTHING RETURNING`; no row back
means it existed) and the cascade handles withdrawal. The dev and test databases need this one table
created (`psql`), which changes a database and needs the user's go-ahead. No existing table changes.

## Code layout (nothing under `app/farm`)

`app/inventory/{application/service.py, infrastructure/repository.py, presentation/{router.py,schemas.py}}`
(raw SQL like `spraying`; `service` calls `catalog_service.get_pesticide` to validate), registered in
`app/main.py`. Tests: repository/service against the test DB, API tests for the three endpoints and
the cascade (`DELETE /me` leaves no inventory rows).

## Documents to update when it is built

`팜가디언_API_명세.md` (25 → 28 APIs, owner table 준혁 16 → 19, a section for the three endpoints,
`DELETE /me` text, 【결정】 marks), `팜가디언_아키텍처.md` §4 tree, §5 schema, §7 API table, README if it
lists tables; Notion 「API 명세서」 (three rows and their pages, same layout as the others); the BE
backlog (one row: 창고 API 구현); `schema.sql`.

## Found while reading `frontend/docs/api-wanted.md` (not part of this design)

1. **Region statistics.** Its 「참고」 table lists 「통계: 읍면별 계통 사용 비중 (`REGION_STATS`)」 as already
   in the spec. It is not: our spec and architecture have no such API, and nothing stores a region.
   `Dashboard.tsx` draws it from mock data. It needs a new design (where the region comes from, how
   other users' spray records are aggregated without exposing them).
2. **OCR match reasons.** The frontend mock shows a reason per candidate (「이름 · 성분 · 회사 일치」,
   「성분만 같아요」, 「이름이 비슷해요」). Our OCR response has only a numeric `score`.
3. **Id types.** The mock uses string ids (`'d-delegate'`, crop `id: "..."`); the real API returns integers.

## Open items only the team can answer

1. Whether the frontend wants region statistics and OCR match reasons built (items 1–2 above). Still open; not part of this work.
2. The backlog id and sprint for this work. (My call: BE-56, S3, P0.)
3. ~~Go-ahead to create the table in the dev and test databases.~~ Given 2026-11-01.
