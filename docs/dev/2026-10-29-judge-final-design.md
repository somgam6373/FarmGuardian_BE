# Judgment overall result — `judge()` (BE-42, design)

- Date: 2026-10-29
- Owner: Junhyeok (judgment context)
- Status: draft, waiting for approval
- Basis: **`팜가디언_API_명세.md` (the frame, unchanged)** §2 (`JudgeResult`), §7; `팜가디언_판정_규칙.md` §2, §5, §9 (V1–V7, R2/R4/R5); the ①②③④ work in `2026-10-29-judge-registration-timing-design.md` and `2026-10-29-judge-count-moa-design.md`

## The API spec is the frame

`팜가디언_API_명세.md` does not change and nothing here edits it. The result of `judge()` is exactly the spec's `JudgeResult`:

```
JudgeResult {pesticide_id: int, moa: Moa|null, verdict: Verdict, checks: [CheckResult],
             notices: [string], data_asof: date}
```

`checks` always has four entries in the order `registration, timing, count, moa`. `data_asof` is shown as 「데이터 조회일」 by the frontend.

## Intent

All four checks exist as separate pure functions. This task joins them into one result: the overall verdict, the notice lines and the data date. After it, the judgment domain is complete and the service (BE-45) only has to feed it inputs and store the result.

## Goals

- `PRIORITY` and `JudgeResult` in `judgment/domain/schemas.py`.
- `overall_verdict(checks) -> Verdict` and `judge(inp) -> JudgeResult` in `judgment/domain/rules.py`.
- Tests: V1–V7 of judgment rules §9, the `verdict` / `notices` parts of R2, R4, R5 that the ①② task left out, and the additions below.

## Non-goals (other tasks)

- Alternatives, `show_extension_office` (BE-44 / BE-45), the notice 「병해충을 지정하면 대안을 볼 수 있습니다」 (judgment rules §5: the **service** adds it when no pest is given and the verdict is `BLOCKED`; the spec's §7 says the same), `rotation_summary` (BE-43).
- Storing the result (`judgment` table), the endpoint, turning static rows into `JudgeInput` (BE-45).
- The disclaimer line (frontend, judgment rules §10-4).

## Behaviour

- `registration = check_registration(inp)`; `timing = check_timing(inp, registration)`; `count = check_count(inp, registration)`; `moa = check_moa(inp)`; `checks = [registration, timing, count, moa]`.
- `verdict` = the status with the highest `PRIORITY` among the four: `BLOCKED` 3, `NEEDS_CHECK` 2, `CAUTION` 1, `OK` 0 (judgment rules §2).
- `notices` = `["병해충을 지정하지 않아 가장 엄격한 기준을 적용했습니다"]` when `pest_id` is None **and** `registrations` is not empty; otherwise `[]` (R5: nothing registered, no notice).
- `data_asof` = `rows_data_asof(inp)`, the same value each check already puts in its `evidence.data_asof` (oldest `data_asof` of the considered rows, `psis_asof` when there are none).
- `pesticide_id` and `moa` are copied from the input.

## Calls I made (please check)

1. `overall_verdict` is a separate public function (not inlined) so the aggregation is tested on every combination of statuses without building inputs, and BE-44's `pick_alternatives` can reuse it.
2. `JudgeResult.checks` is limited to exactly four entries in the type (`min_length = max_length = 4`), so the spec's "항상 4개" cannot be broken by a later change.
3. `judge()` does not add the service notice for an unspecified pest (see non-goals); R-case expectations below only assert the notice the domain owns.
4. No test builds `JudgeInput` from the static JSON here; that conversion is production code of BE-45, which will carry the real-data smoke test.

## Tests

- V1–V7 as written in judgment rules §9, driven through `judge()`.
- R2: `verdict = BLOCKED`; R4: `verdict = NEEDS_CHECK` and the notice; R5: `BLOCKED`, `notices = []`.
- Every combination of the four statuses (256) gives the status with the highest priority.
- The result serializes to the spec shape: keys `pesticide_id, moa, verdict, checks, notices, data_asof`; check keys in order; dates as ISO strings; `moa` as `{label_kr, system, code}` or null.
- A result with a number of checks other than four is rejected.
- `judge()` leaves its input unchanged (the models are frozen) and gives equal results for equal inputs.

## Left to the builder

Names of test builders and files (`tests/test_judge_result.py`), the exact helper layout.

## Open questions (not blocking)

- None new. The notice for unspecified pests that the service adds is specified in judgment rules §5 and built in BE-45.
