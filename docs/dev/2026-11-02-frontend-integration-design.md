# Frontend prototype ↔ API integration (design)

- Date: 2026-11-02
- Owner: Junhyeok (backend lead; `catalog`, `judgment`, `spraying`, `identity` contexts) + frontend wiring
- Status: **draft; C1 approved 2026-11-02.** The open items at the end need a team answer before the matching tasks start.
- Basis: a screen-by-screen read of `frontend/src` (10 screens, `AppState`, `mock.ts`, `lib/verdict.ts`) against the
  27 implemented endpoints (`GET /zones/{id}/weather` is in the spec but not built, which is why weather stays mock);
  `팜가디언_API_명세.md`, `팜가디언_판정_규칙.md`, `팜가디언_아키텍처.md`, `팜가디언_PRD_수정_제안.md`,
  `팜가디언_사용자_시나리오.md`; the static catalog in `app/catalog/data`.
- Rule applied: when UI and API disagree, **keep the prototype UI** and extend the backend that is ours. Anything
  under `app/farm` (Hyebin's) is **not edited by us**; it is listed in `팜가디언_혜빈님_요청_프론트연동.md`.
  What the documents leave open, the team decides (`【결정】`).
- Product constraints this design must not break (from the baseline documents):
  - Missing data never passes as OK; it is `NEEDS_CHECK`. A wrong 「가능」 is the dangerous error. The user picks the
    drug; nothing recommends one. Judgment text avoids 추천·예측·확률·안전 (judge_rules §7, §8), and the UI copy should too.
  - P1, out of scope: zone re-split and zone deletion (PRD 수정 제안 #5), dilution calculation (아키텍처 §1), line-drawing split.
  - First use goes through onboarding: sign up → split zones → past sprays and 「누락 없음」 → `POST /me/onboarding`
    (아키텍처 §2, PRD 수정 제안 #9, 명세 §9).

## Intent

The frontend is a hard-coded prototype: no `fetch`, every screen reads `data/mock.ts` and evaluates verdicts on the
client (`lib/verdict.ts`). The backend API is done. This design decides, per gap, how the prototype is wired to the
real API, which backend pieces we add, and which prototype pieces we drop. Success: every screen runs on the real
API except the two parts kept as mock (weather card, neighbour statistics) and the landing-page demo.

## Decisions (made with the user, 2026-11-02)

| # | Topic | Decision |
|---|---|---|
| 1 | Default rule | Keep prototype UI; extend our backend; Hyebin's area is documented separately |
| 2 | Login | Kakao button → ID/password form (+ signup). Guest browsing removed |
| 3 | Verdict lists | New read-only batch judgment API (B1) |
| 4 | Drug info | Add company, ingredients, kind, form (B2) and the label's dilution text (B3). **Content (함량 25%) dropped. Water volume (「물 N L」) dropped** (dilution calculation is P1; the 200 L/10a it used was an assumption) |
| 5 | Harvest date | Zone gets `harvest_at` (Hyebin) and ② uses it (**C1, approved 2026-11-02**). A zone without `harvest_at` keeps today's ② |
| 6 | Spray records | Store `pest_id`; soft cancel + restore (B4) |
| 7 | Neighbour statistics | Stays mock (like weather) |
| 8 | Crops | Only the 3 in the catalog (`GET /crops`: 감자 1, 배추 2, 토마토 3) |
| 9 | Pest card | Add `months`, `pesticide_count`, virus flag; **peak emphasis dropped** (B5) |
| 10 | 「심을 때」 status | Derived in the frontend (planted_at empty, or drug is `at_planting_only`). A ① `BLOCKED` still shows 불가 (priority 불가 > 심을 때, as in the prototype) |
| 11 | OCR match reason | Backend returns which fields matched (B6) |
| 12 | Past-record drug picker | Crop-registered drugs only (two `GET /pesticides` calls), shown as a searchable list (the crop-wide call returns 508–1008 drugs) |
| 13 | Onboarding gate | **Original decision restored.** `GET /me` `onboarded=false` → onboarding; tabs stay locked until `POST /me/onboarding` succeeds (see 「Onboarding and 누락 없음」) |
| 14 | Field without zones | Adding a farm later reuses the onboarding split step. If the user leaves midway the field keeps `zones=[]` and the UI shows a 「구역 나누기 이어하기」 card |
| 15 | Field address | Stored on the server: Hyebin #3 option B plus the identity part (B11). Closes the "미정" line in 아키텍처 §8 |
| 16 | Zone deletion | None (P1, PRD 수정 제안 #5). A wrongly split field is deleted and created again. The frontend drops the 「구역 삭제」 button |
| 17 | Virus pests in the pest list | `GET /pests` also returns pests that appear as a virus in `virus_vector` (B10) |
| 18 | Judgment response | Carries the chosen drug (B8); responses are gzipped (B9) |

## Goals

1. Each screen below works on the real API.
2. Backend additions are additive: no existing field changes meaning, `app/farm` files are untouched.
3. The server verdict replaces the client's `evaluate()` everywhere.

## Non-goals

- Real weather and neighbour statistics (kept as mock, labelled as sample data in the UI).
- Kakao OAuth, guest mode, a demo account, content (함량) data, peak-month data, crops other than the 3.
- Zone deletion or re-split, dilution calculation and water volume (P1).
- Anything in `app/farm` (see the Hyebin document).

## Conflicts with existing documents

**C1. ② timing and the harvest date (approved 2026-11-02).** `팜가디언_판정_규칙.md` §1/§4 ② decided: the harvest date is
**not** an input, ② shows `harvest_from` and **never returns `BLOCKED`**. Decision 5 reverses that. Rule, mirroring the
prototype's thresholds: when `zone.harvest_at` is set and the strictest `phi` is known,
`margin_days = (harvest_at − today).days − phi`; `margin < 0` → `BLOCKED`, `0 ≤ margin ≤ 2` → `CAUTION`, otherwise `OK`;
`facts` gain `harvest_at` and `margin_days`. **With no `harvest_at`, ② behaves as today** (OK with `harvest_from`), so the
prototype's 「수확일 모름 = 확인 필요」 disappears. The reason is the product's core risk (a harvest before the pre-harvest
interval is a shipping ban). Touches: judge_rules §1 table, §4 ②, §9 cases; 아키텍처 §2 (② 시기 row);
`rules.py`; `팜가디언_PRD_수정_제안.md`; `ZoneContext` in `app/farm/application/zone_reader.py` (Hyebin).
**Fallback if Hyebin does not deliver `harvest_at`:** store nothing, leave ② unchanged, hide 「여유 N일」 and 「수확 D-N」.

**C2. 「취소 = 삭제」.** The API spec says cancelling a record deletes it (명세 §8, 아키텍처 §2). B4 changes that to a soft
cancel (row kept, restorable). The Settings screen's note 「취소한 기록도 삭제 없이 보존」 becomes true.

**C3. Judgments are saved.** `POST /zones/{id}/judgments` stores every call (아키텍처 §5). The Verdict screen keeps using it
(one call per screen view); lists use B1, which stores nothing. Side effect to accept: `last_judgment` on the home
summary becomes "the last drug the user opened", the risk 아키텍처 §10-6 already names.

**C4. `GET /pests` wording.** 아키텍처 §7 and 명세 §6 say `GET /pests` lists the crop's pests that have a registered drug.
B10 adds virus pests (none has a registered drug), so both sentences and three tests change.

**C5. Field address.** 아키텍처 §8 (브이월드 지오코더) lists "주소를 어느 응답에 넣을지" as open. Decision 15 closes it:
`address` on `POST /fields`, signup and `FieldOut`.

## Backend changes (ours)

### B1. Batch judgment preview — `GET /zones/{zone_id}/judgments/preview` (judgment)

- Query: `pest_id` (**required** 【결정】: a crop-wide pool is 508–1008 drugs), `apply_date` (optional, same rule as the POST).
- Response 200: `[{pesticide: PesticideDetail, at_planting_only: bool, result: JudgeResult}]`, ordered as `GET /pesticides`
  (moa → item → brand). Same pool as `catalog_service.list_pesticides(crop_id, pest_id)`.
- Pool sizes per (crop, pest), measured on the static data: 91 pairs, median 18 drugs, max 274 (배추 × 배추좀나방,
  the prototype's default pest), 9 pairs above 100. Every item carries a full `JudgeResult`, so the response is gzipped
  (B9) and the frontend fetches it **once per (zone, pest)** and shares it between MapHome (uses 3), DrugList and
  Dashboard (uses 2).
- Saves nothing. Reads the zone context and spray history **once**, then runs `judge()` per drug in memory.
- Errors: 401, 404 (zone not owned / unknown pest or pest of another crop), 422 (missing `pest_id`; `apply_date` > 2100-12-31).
- Used by: MapHome sheet (top 3), DrugList (groups and tally), Dashboard 「다음에 쓸 약」.
- Code: a `preview()` next to `run_judgment()` in `judgment/application/service.py`, sharing `assess()`'s `judged()`.

### B2. `PesticideDetail` (catalog)

`PesticideDetail(PesticideBase)` adds `company: str | None`, `form: str | None`, `ingredients: list[str]`,
`kind: "insecticide" | "fungicide" | "both" | null`. `PesticideOut` extends it (adds `at_planting_only`).
Used in: `GET /pesticides`, judgment `alternatives`, the judgment response (B8), preview, OCR candidates, `SprayOut.pesticide`.
**`PesticideBase` stays as is**, because `LastSpray` in `app/farm/presentation/schemas.py` uses it, so `GET /fields` is unchanged.

Derivation (checked against the data: 1363 drugs):

| Field | Source |
|---|---|
| `form` | last space-separated token of `item_name` (all 1363 have a space; 25 forms, e.g. 액상수화제) |
| `ingredients` | `use_ingredient` by `seq` → `ingredient.name` (rows of one drug never disagree; every drug has at least one) |
| `kind` | `pesticide_use.usage`: 살충→insecticide, 살균→fungicide, 균충→both (never differs within a drug) |
| `company` | company of the drug's first row (lowest `use_id`) 【결정】; 83 drugs have 2+ companies |

### B3. Dilution text — `facts.dilution` on the ① `registration` check

String, the raw `dilut_raw` of the first considered row (the row already used for `evidence`), or null. It repeats
what `evidence.source_text` already shows (「사용방법 · 희석」) but as its own key, so the frontend need not split the string.
Display rule (frontend, 【결정】), on 4133 rows: text starting with `N배` (3665 rows, e.g. `2000배 -`) → 「희석 N배」;
text starting with `-` (467 rows, granules and dusts: a per-10a amount such as `- 6㎏/10a`) → the raw text under
「사용량」; the one odd value (`2,000배배`) → raw text. **No water volume is computed.** Needs the ① facts table in
judge_rules §4 and 명세 §7 updated.

### B4. Spray records: `pest_id` and soft cancel (spraying)

- Schema (`schema.sql`, `spray_log`): `pest_id int NULL` (static pest id, no FK), `cancelled_at timestamptz NULL`.
- `POST /zones/{id}/sprays` body gains `pest_id?: int|null` (unknown id → 422 `loc ["body","pest_id"]`; existence check only 【결정】).
- `Spray` (POST/GET response) gains `pest: {id, name} | null` and `cancelled: bool`; `pesticide` becomes `PesticideDetail`.
  `ZoneSummary.last_spray` in `GET /fields` keeps its old four-key shape (it uses `PesticideBase`), so 명세 §2 must say so.
- `GET /zones/{id}/sprays` returns cancelled rows too (`cancelled: true`); `total` counts them. Order unchanged.
  The frontend counts active rows itself (「올해 N회」).
- `DELETE /zones/{id}/sprays/{sid}` → sets `cancelled_at`, still 204 (already cancelled → 204 too 【결정】); 404 as before.
- New `POST /zones/{id}/sprays/{sid}/restore` → 200 `Spray`; 404 if not found. Restoring may create a same-day same-drug pair; allowed 【결정】.
- **Cancelled rows are excluded from everything that decides**: `spray_service.history()` (judgment input and, through
  `judgment/application/reader.py`, the rotation summary), `find_duplicate`, and `list_sprays()` by default. The router for
  `GET /sprays` passes `include_cancelled=True`. This keeps `zone_service._last_spray` (Hyebin's file) correct **without editing it**.
- `request_id` replay still returns the original row even if it was cancelled since (shows `cancelled: true`) 【결정】.
- Existing tests that assume "cancel = delete" must be rewritten (listed in the plan, Task 6).
- The dev and test databases need the two columns (`ALTER TABLE`); teammates run it too. Needs the user's go-ahead.

### B5. Pest card (catalog)

`PestCard` / `PestCardOut` gain: `months: [int]` (from the chosen season row, `[]` when none; 49 of 129 pests have one),
`pesticide_count: int` (drugs registered for that crop × pest; 0 if none), `is_virus: bool` (id in `virus_vector.virus_pest_id`;
6 virus ids, 5 with a vector, id 64 has none), `carries: [{id, name}]` (viruses this pest vectors, from
`virus_vector.vector_pest_id`). `kind`, `occurrence` and the rest are unchanged. No `peak`. `pesticide_count` should come
from a cached per-(crop, pest) count, not a scan per card 【builder's call】.

### B6. OCR match reason (catalog)

Each candidate gains `matched: ["brand" | "product" | "company", …]`. A field counts when the read value and the drug's
`name` / `item_name` / `company` have normalized similarity ≥ 0.9 【결정, tune with real photos like `CUTOFF`】. `score` and the
ranking do not change. If a drug has several companies, any one may match.

### B7. ② harvest margin (judgment) — C1, approved

As written in C1. Depends on Hyebin adding `harvest_at`.

### B8. The judgment response carries the chosen drug (judgment)

`JudgeResponse` gains `pesticide: PesticideOut` (the `GET /pesticides` item shape, including `at_planting_only`).
`at_planting_only` for the chosen drug = it has at least one considered registration row (the crop's rows, narrowed to
`pest_id` when given) and every one of them is `stage`. Why: the Verdict screen needs name, form, company and ingredients,
and `/verdict/:drugId` is reached by refresh or by OCR with no list data; today `JudgeResponse` has only
`result.pesticide_id`. This also answers how the screen learns `at_planting_only` for an OCR drug. Contract change:
`openapi.json` PR needs frontend approval (아키텍처 §9).

### B9. Gzip (core)

`GZipMiddleware(minimum_size=1000)` in `app/main.py`. The preview (B1) is the reason; all responses benefit.

### B10. Virus pests in `GET /pests` (catalog)

`list_pests` returns the crop's pests that have a registered drug **or** appear as a virus in `virus_vector`. All six
virus pests have no registered drug, so today they appear only under a symptom part (`GET /pests/candidates`) and a name
search for 「모자이크병」 finds nothing. Result per crop: 감자 25 (unchanged), 배추 43 → 45, 토마토 23 → 27. Virus cards
come back with `pesticide_count = 0`. Order and the `q` filter are unchanged. Changes 아키텍처 §7, 명세 §6 (C4).

### B11. Field address through signup (identity) — depends on Hyebin #3

`POST /auth/signup` body gains `field_address?: string` (stripped, 1–200 characters when given, like `field_name`).
`identity.service.signup` passes it to `field_service.create_field(..., address=...)`. `POST /fields` and `FieldOut`
carry `address` (Hyebin). Fields created before this change have `address = null`. If Hyebin declines #3, this item is
dropped and the frontend keeps the address in the browser (Hyebin #3 option A).

## Onboarding and 누락 없음

The prototype has neither step, but the baseline documents define both (사용자 시나리오 B, 명세 §9):

1. After login or signup the frontend calls `GET /me`. `onboarded=false` → onboarding; the tabs stay locked.
2. **Split.** The field has `zones=[]`. Direction (`crosswise` / `lengthwise`) plus a ratio slider per zone, previewed with
   `POST /fields/{id}/split-preview`, then `POST /fields/{id}/zones` with a name, crop and optional 심은 날 per zone.
   Zones are strips (max 10); the prototype's grid with two slider axes is replaced (Hyebin #4, option A; PRD 수정 제안 #1).
3. **Past sprays and 누락 없음.** Per zone, past records are added with the History 「지난 기록 추가」 sheet, then
   `PATCH {history_confirmed: true}`. Set 심은 날 first: changing it resets the confirmation.
4. `POST /me/onboarding`. `422 ONBOARDING_INCOMPLETE` carries `unconfirmed_zone_ids`; mark those zones. Calling it again
   after success is a 200 no-op.

Without 「누락 없음」 the server returns 확인 필요 for ③④ on every drug, so the confirmation is required, not optional.
After onboarding it comes back only when a zone's `planted_at` changes (also when the crop changes, which clears
`planted_at`) or when a new farm is added: History and the zone editor show a banner that calls the same `PATCH`.
Adding a farm later reuses the split step and the parcel picker (`matches_query`, `used_by_field_id` → 「사용 중」,
`409 PARCEL_ALREADY_USED`). A field saved but not yet split shows the 「구역 나누기 이어하기」 card.

## Frontend changes (by screen)

| Screen | Change |
|---|---|
| (all) | New `api/` layer: base URL (Vite proxy, or add `http://localhost:8443` to `CORS_ORIGINS` — `.env.example` says 3000 and the dev server is fixed to 8443), `X-User-Id` from storage, error mapper for `{error:{code,…}}`; ids become numbers; remove `TODAY` (use KST today); server state replaces `mock.ts` in `AppState` (selected zone/pest stay local). Route guard: no stored id → `/`; `onboarded=false` → onboarding. `mock.ts` stays only for the Login landing demo (`ZONES`, `drugById`) |
| Login `/` | Replace Kakao and 「둘러보기」 with login + signup. Signup = address search → parcel pick (several parcels, `matches_query`) → field name → `POST /auth/signup` (with `field_address` = the chosen `jibun_addr`) → onboarding |
| Onboarding (new) | See 「Onboarding and 누락 없음」 |
| MapHome | Farm card/zones from `GET /fields`; `FieldMap` draws `geometry`; top-3 drugs from B1; sheet shows 심은 날 and 「수확 D-N」 (needs `harvest_at`); **weather stays mock**. `FieldMap` needs real work: the prototype uses fixed 0–400 coordinates, a hard-coded terrain, roads and 「선자령길/횡계천」 labels and one polygon per zone, while the API gives EPSG:5179 metre `MultiPolygon`s (normalise coordinates, flip y, scale pattern and stroke, handle several parts) |
| ScanSheet | Upload to `POST /ocr/pesticide-labels`; lines = `read.text` split by newline; candidate text from `matched` (table below); 「예시 사진」 stays a labelled canned result 【결정】 |
| PestSelect | Parts from `symptom-parts`: the API has **six** (덩이, 뿌리, 잎, 줄기, 벌레, 열매; 벌레 is 27 of 배추's 52 pests, 덩이 is 감자 only), the prototype four — add two buttons and icons. List from `candidates` or `pests` (both filters combined client-side). `MonthBar` from `months` (no peak; 80 of 129 pests have none, so guard the empty case instead of `Math.min(...[])`); count from `pesticide_count`; virus tag/notes from `is_virus`, `vectors`, `carries`; use the fixed 매개충 sentence of judge_rules §8 plus `vectors[].guide` |
| DrugList | B1 groups and tally; 「심을 때」 derived; card fields from `PesticideDetail` |
| Verdict | `POST /judgments`; header and 「약 정보」 from `response.pesticide` (B8); checks mapped by key; chips rebuilt from `facts`; alternatives from the response; record button sends `request_id`, `pest_id`, `source:"app"`; **remove the `doneToday` button lock** so the server's 409 dialog (기존 기록 확인 / 별도 살포로 저장 / 돌아가기) is reachable; 창고 button calls the inventory API |
| History | Per-zone `GET /sprays` merged for 「전체」 (paged, `limit` ≤ 100); count active rows only; pest column; soft cancel/restore; add form: pest from `GET /pests`, drug from two `GET /pesticides` calls shown as a searchable list; 「누락 없음」 banner |
| Fields | `PATCH /zones/{id}` with an explicit save (not per keystroke); name `maxLength` 30; **no 「구역 삭제」 button** (decision 16); crop change warning says 「기록은 남고, 심은 날과 누락 없음을 다시 확인해야 해요」 (PRD 수정 제안 #6); farm creation = save field, then split; 「구역 나누기 이어하기」 card for a field with `zones=[]`; remove `plannedAt` (Hyebin #6) |
| Dashboard | Totals from `GET /zones/{id}` `rotation`; drug names per group from sprays; 「다음에 쓸 약」 from B1; **neighbour card stays mock** |
| Settings | Account copy for ID/password; 로그아웃 clears the stored id; add 회원 탈퇴 (`DELETE /me`) with a confirm screen; fix the 카카오 line in the privacy list |
| Inventory (new wiring) | `GET /inventory` on start gives the drug-id list; Verdict toggles with `POST /inventory` / `DELETE /inventory/{drug_id}`; MapHome, DrugList and Dashboard use it for the badge and the within-group order. The backend is done (명세 §8); `frontend/docs/api-wanted.md` item 2 is answered by it, and `GET /crops` (item 1) by the crop list |
| Copy review | Check against judge_rules §7/§8: Dashboard 「다음에 쓸 약」 and 「다른 그룹을 먼저 보여 드려요」 read as a recommendation (the server sorts only by moa → item → brand "because other orders look like a recommendation"); the neighbour card's 「처음 써도 덜 들을 수 있어요」 is a resistance prediction while Settings says 「저항성 예측: 안 함」; VirusSheet's 「번지는 걸 막을 수 있어요」 is not from the data. Decide wording with the frontend before shipping |

Status mapping: `OK→ok`, `CAUTION→caution`, `BLOCKED→no`, `NEEDS_CHECK→unknown`; `preplant` is derived (decision 10).
Check keys: `reg→registration`, `timing→timing`, `count→count`, `group→moa`. `PestCard.kind` is `병` / `해충` / null: 해충 → 벌레, `is_virus` → 바이러스.

OCR copy: all three of brand/product/company → 「이름 · 성분 · 회사 일치」; `product` only → 「성분만 같아요」; otherwise → 「이름이 비슷해요」 【결정】.

## Behaviour that changes when the server judges

| Prototype (client) | Server (judge_rules) | UI effect |
|---|---|---|
| ③ last allowed use → `caution` | `OK` with a message | badge stays 가능; text says 마지막 횟수 |
| ③ counted per ingredient | counted per `item_name` | counts can differ |
| ④ twice in a row → `no` | `CAUTION` only, rule per MOA (§4 ④) | no 불가 from ④ |
| ④ over this season | window ignores season (§4 ④: "작기와 무관") | — |
| not registered → ②③④ `skip` | ① `BLOCKED`; ②③ `NEEDS_CHECK`; ④ still computed | 「해당 없음」 becomes 「자료 없음」 for ②③ |
| no 누락 없음 concept | ③④ `NEEDS_CHECK` until confirmed | onboarding step and banner |
| `harvestAt` margin → `no`/`caution` | ② never blocks | with C1 (approved) only when `harvest_at` is set |
| `harvestAt` empty → ② `unknown` (「수확일 모름」) | ② `OK` with `harvest_from` (today's rule) | such zones show 가능 where the prototype showed 확인 필요; show a hint 「수확 예정일을 넣으면 여유 일수를 계산해요」 that is not a status |
| 「물 N L」 from area × 0.2 | not provided | removed; raw label text only |
| cancelled = struck-through, kept | soft cancel (B4) | same look; now stored |

## Docs to update when built

`팜가디언_API_명세.md` (28 → 30 endpoints counting the unbuilt weather one; spray section; `Pesticide`/`PestCard` types;
`ZoneSummary.last_spray` stays the old shape; `GET /pests` incl. viruses; `JudgeResponse.pesticide`; §7 facts; 취소 wording;
field `address` if B11 lands), `팜가디언_판정_규칙.md` (③ facts, ① `dilution`, ② margin), `팜가디언_아키텍처.md` (§2 ② row
and 취소 row, §5 `spray_log` and `field`, §7 `GET /pests` and the table, §8 address 미정),
`팜가디언_PRD_수정_제안.md` (note: it is in `.gitignore`, so it is edited locally and not committed),
`schema.sql`, `api_playground.html` if it lists these APIs, Notion 「API 명세서」, the BE backlog (one row per B-item).

## Open items only the team can answer

1. ~~C1~~ approved 2026-11-02.
2. Go-ahead to run the `ALTER TABLE` statements in the dev and test databases: `spray_log` (B4) now, `field.address` (B11) once Hyebin accepts #3.
3. Backlog ids and sprint for B1–B11.
4. Hyebin: confirm #1 (`harvest_at`) and #3 (`address`); answer #4 (split as strips) and #6 (drop `plannedAt`). #2 is settled (no zone deletion), #5 follows PRD 수정 제안 #6.
5. Frontend team: the onboarding screens, the parcel picker, the split direction wording and the copy review above. These are on the 「프론트와 합의」 list in 아키텍처 §10-6.

## Left to the builder

The cached per-pest drug count (B5); the exact similarity function and threshold for B6.
