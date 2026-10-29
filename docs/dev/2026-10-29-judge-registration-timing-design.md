# Judgment ① registration and ② timing — BE-38 / BE-39 (design)

- Date: 2026-10-29
- Owner: Junhyeok (judgment context)
- Status: draft, waiting for approval
- Basis: **`팜가디언_API_명세.md` (the frame, see below)**; `팜가디언_판정_규칙.md` §1–4, §8, §9; `2026-10-29-static-catalog-design.md`

## The API spec is the frame

Decided by Junhyeok on 2026-10-29: `팜가디언_API_명세.md` is the contract with the frontend and **does not change**. Everything here is built to fit it:

- A check result has exactly the spec's shape: `CheckResult {key, status, message, facts, evidence}` with `key` = `registration` / `timing`, `status` ∈ `OK | CAUTION | BLOCKED | NEEDS_CHECK`, `evidence {source_text, data_asof}`.
- `facts` use exactly the keys of the spec's §7 table. `registration`: `{crop_registered, pest_specified, registered_pests, rows}` (only the keys the case defines, as the spec allows). `timing`: always all five of `{phi_days, harvest_from, rows, strict_use_method, no_limit}`, `null` when empty.
- Dates inside `facts` are ISO strings; `Evidence.data_asof` is a `date`.
- `message` wording follows judgment rules §8; the spec only says `string`.
- No file named `팜가디언_API_명세.md` is edited by this work. If another document disagrees with the spec, the spec wins and the other document is fixed. One known wording gap is left alone: spec §10 (a 참고 table) says "미리 적재한 DB" for 병해충·약제·판정, while the data is static JSON in memory (`static-catalog-design`). The contract in that row, no external call while serving a request, still holds.

## Intent

Build the first two of the four checks as pure, tested functions so the riskiest part of the service (a wrong "OK" for a pesticide) is pinned by a table of cases before any API exists.

## Goals

- `judgment/domain/schemas.py`: the types the two checks need (below).
- `judgment/domain/rules.py`: `check_registration` (①) and `check_timing` (②) with the exact conditions, messages, `facts` and `evidence` of judgment rules §4 and §8.
- Tests: the ① and ② rows of judgment rules §9 (R1–R5, T1–T14) as parametrized tables, plus the additions below.
- No database, no HTTP, no clock: `today` is an input.

## Non-goals (other tasks)

- ③ count (BE-40), ④ action group (BE-41), `judge()`, `JudgeResult`, the overall `verdict`, `notices`, `JudgeResult.data_asof` and `show_extension_office` (BE-42), rotation (BE-43), alternatives (BE-44).
- Turning static JSON rows into `Registration` objects, `Moa` conversion, the judgment service and `POST /zones/{id}/judgments` (BE-45). The mapping is fixed below so BE-45 does not have to decide it.
- Parts of R2, R4, R5 that assert `verdict` or `notices` (BE-42). Their ① and ② parts are tested here.

## Types (`schemas.py`, Pydantic v2, frozen)

`Verdict` (StrEnum: `OK`, `CAUTION`, `BLOCKED`, `NEEDS_CHECK`), `Moa`, `Registration`, `SprayRecord`, `JudgeInput`, `Evidence`, `CheckResult` — field names and types exactly as judgment rules §2, so BE-40/41/42 add to them without renaming. `JudgeResult` and the rotation types are not defined yet.

## Functions (`rules.py`)

- `check_registration(inp: JudgeInput) -> CheckResult`
- `check_timing(inp: JudgeInput, registration: CheckResult) -> CheckResult` — ② is `NEEDS_CHECK` "등록 정보가 없어 확인할 수 없습니다" when `registration.status` is `BLOCKED`.
- Shared helpers that BE-42 reuses: `considered_rows(inp)` (rows of the chosen pest, or all rows when no pest), `calc_rows(rows)` (judgment rules §3: drop `AT_PLANTING`, then `NO_LIMIT`, only while rows remain), `rows_data_asof(inp) -> date` (oldest `data_asof` of the considered rows, `psis_asof` when there are none) used for `evidence.data_asof`.
- Date text in messages: same year as `today` → `10월 11일`, otherwise `2027년 1월 8일`.

## Mapping of static rows to `Registration` (decided here, built in BE-45)

One `Registration` per `pesticide_use` row joined to its `safe_use_std` row by `use_id`, for the chosen (`product`, `brand`) and the zone's crop (`pest.crop_id`):

| `Registration` | from |
|---|---|
| `pest_id`, `pest_name` | `pesticide_use.pest_id`, `pest.name` |
| `phi_days`, `max_uses` | `safe_use_std.phi_days`, `max_count` |
| `use_suittime_raw`, `use_num_raw`, `dilut_raw`, `use_method` | `use_time`, `use_count`, `dilution`, `method` |
| `usage_type` | `parse_status`: `ok` → `NORMAL`, `stage` → `AT_PLANTING`, `no_std` → `NO_LIMIT`, `failed` → `CHECK` |
| `data_asof` | `safe_use_std.base_date` |

Checked against all 4,133 rows: every `ok` row has `use_time` "수확N일전" and `phi_days` = N; every `stage` row is a 정식/파종 expression; every `no_std` row has `use_count` "-" and `use_time` 발생초기 (the judgment rules' `NO_LIMIT` example); the 7 `failed` rows are the "확인 필요" rows. Rows are ordered by `use_id`. 100 (pest, product, brand) groups have more than one `use_method`, so the "가장 엄격한 값" and "(… 기준)" rules matter on real data.

## Calls I made (please check)

1. **Scope** is types + the two check functions + tests; the row mapping and the service stay in BE-45.
2. **`facts.rows` = number of considered rows** (`considered_rows`, before `calc_rows` drops any), for both ① and ②. Judgment rules do not say which; the spec only says `int`.
3. **`CHECK` rows are NULL whatever numbers they carry**, as judgment rules §3 says. Real data has one: `use_id` 3539 (`phi_days` 50, count "연1회"). It must give ② `NEEDS_CHECK`. This is an addition to the §9 table (T15).
4. A message scan test: every ① and ② message produced by the test cases contains none of the forbidden words `추천 예측 예상 가능성 위험 확률 안전 문제없` (judgment rules §8).
5. `Verdict` is a `StrEnum` (judgment rules write `(str, Enum)`); it serializes identically.
6. Test files `tests/test_judge_registration.py` and `tests/test_judge_timing.py`, with a small builder for the §9 `base` fixture shared between them.

## Left to the builder

File layout of the shared test builder, the message templates as constants or inline, exact helper names beyond those listed.
