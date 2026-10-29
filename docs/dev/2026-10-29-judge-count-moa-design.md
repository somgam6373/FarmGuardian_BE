# Judgment ③ count and ④ action group — BE-40 / BE-41 (design)

- Date: 2026-10-29
- Owner: Junhyeok (judgment context)
- Status: draft, waiting for approval
- Basis: **`팜가디언_API_명세.md` (the frame, unchanged)**; `팜가디언_판정_규칙.md` §3, §4 ③④, §8, §9 (C1–C21, M1–M17, RULE1, MSG1); `2026-10-29-judge-registration-timing-design.md`; `2026-10-29-static-catalog-design.md`

## The API spec is the frame

Same rule as the ①② work: `팜가디언_API_명세.md` does not change and nothing here edits it.

- Results are the spec's `CheckResult {key, status, message, facts, evidence}` with `key` = `count` / `moa`.
- `facts` use exactly the keys of the spec's §7 table, always all of them, `null` where a value does not exist (the spec: "값이 없으면 null이다"). `count`: `{used, max_uses, remaining, remaining_after, since, item_name, strict_use_method, no_limit}`. `moa`: `{label, rule, max_consecutive, consecutive, unknown, window: [{id, sprayed_on, item_name, label}]}`.
- Dates inside `facts` (`since`, `window[].sprayed_on`) are ISO strings; `Evidence.data_asof` is a `date`.
- `Moa` stays `{label_kr, system, code}`: the spec has no "multi-site" field, so the rule table below is decided from the label (and `system` for IRAC) only.

## Intent

Finish the two checks that depend on the spray history: how many times this item was already sprayed this season (③) and whether the same action group is being repeated (④). Like ①②, they are pure functions pinned by the §9 tables.

## Decision made with Junhyeok

- The ④ rule table is followed as written in judgment rules §4 ④. Groups that are not in the table, including 생1 and 생2 (FRAC BM, about 9 rows) that the data owner marked as multi-site, are "그 밖의 계열": at most 1 in a row.

## Goals

- `rotation_rule(moa) -> RotationRule`, `check_count(inp, registration) -> CheckResult`, `check_moa(inp) -> CheckResult` in `judgment/domain/rules.py` with the conditions, messages, `facts` and `evidence` of judgment rules §4 and §8.
- The ③ rows (C1–C21), ④ rows (M1–M17), RULE1 and MSG1 of §9 as tables, plus the additions below.
- A check that the hard-coded rule table agrees with the delivered `rotation_rule.json`, and that every `moa.json` row gets a rule.

## Non-goals (other tasks)

- `rotation_summary` (BE-43), `judge()`, `JudgeResult`, overall `verdict`, `notices` (BE-42), alternatives (BE-44), the judgment service and API, turning static rows into `Registration` / `SprayRecord` / `Moa` objects (BE-45).
- The 「시즌 최대」 and 「같은 세대(약 30일) 안」 conditions of `rotation_rule.json`: not applied (judgment rules §4 ④, §10-9). Only the source text keeps them.
- Editing the spec, `schemas.py` types other than adding `RotationRule`.

## ③ count (`check_count`)

`rows = considered_rows(inp)`, `calc = calc_rows(rows)` (same helpers as ②). Conditions, first match wins (judgment rules §4 ③):

| # | Condition | status |
|---|---|---|
| 1 | `registration.status` is BLOCKED (or no rows) | NEEDS_CHECK, 「등록 정보가 없어 확인할 수 없습니다」, evidence 「없음」 |
| 2 | every `calc` row is `NO_LIMIT` | OK, 「사용 횟수 제한이 없는 약제입니다. 라벨의 사용 방법을 확인해 주세요」, `no_limit` true. Independent of `planted_at` and `history_confirmed` |
| 3 | a `calc` row has no number (`max_uses` None or `usage_type == CHECK`) | NEEDS_CHECK, 「최대 사용 횟수 기준을 읽지 못했습니다. 원문: {raw}」 |
| 4 | `planted_at` is None | NEEDS_CHECK, 「정식일이 없어 이번 작기 사용 횟수를 셀 수 없습니다. 정식일을 입력해 주세요」 |
| 5 | `history_confirmed` is false | NEEDS_CHECK, 「살포 기록에 빠진 것이 없는지 확인되지 않았습니다. 기록을 입력하고 「누락 없음」을 선택해 주세요」 |
| 6 | `used >= max` | BLOCKED, 「{since}부터 {used}회 사용해 최대 {max}회를 채웠습니다. 남은 횟수는 0회입니다」 |
| 7 | otherwise | OK, `remaining >= 2`: 「남은 횟수 {remaining}회, 이번 사용 후 {remaining_after}회입니다 (최대 {max}회)」; `remaining == 1`: 「남은 횟수 1회, 이번 사용 후 0회입니다 (최대 {max}회). 이번이 마지막 사용입니다」 |

- `max` = smallest `max_uses` of `calc`; the strict row is the first `calc` row with that value (`strict_use_method` = its `use_method`). `{raw}` = `use_num_raw` of the first unreadable `calc` row, 「없음」 if empty. `evidence.source_text` = strict row's `use_num_raw` (rows 3: the unreadable row's), 「없음」 for #1 or when empty; for #2 the first `calc` row's.
- `used` = number of `history` records with `item_name == inp.item_name` and `sprayed_on >= planted_at` (same day twice = 2; before `planted_at` ignored). `remaining = max - used` (0 when blocked, even if over), `remaining_after = remaining - 1`, None when blocked. `since` text uses `format_date_kr(planted_at, today)`.
- When `calc` has two or more distinct non-empty `use_method` values and the strict row's is not empty, the OK and BLOCKED messages (not the NO_LIMIT one) end with ` ({use_method} 기준)`.
- `facts` always has all eight keys. `item_name` and `since` (ISO date or None) are always set; `used`, `max_uses`, `remaining`, `remaining_after` are None when the status is NEEDS_CHECK or the check is NO_LIMIT (nothing reliable to count); `no_limit` is true only for #2; `remaining_after` is None when blocked.

## ④ action group (`check_moa`)

Independent of ① and ②. Conditions, first match wins (judgment rules §4 ④):

| # | Condition | status |
|---|---|---|
| 1 | `inp.moa` is None | NEEDS_CHECK, 「이 약제의 작용기작 정보가 없어 비교할 수 없습니다」, evidence 「없음」 |
| 2 | `history_confirmed` is false | NEEDS_CHECK, 「살포 기록에 빠진 것이 없는지 확인되지 않았습니다. 기록을 입력하고 「누락 없음」을 선택해 주세요」 |
| 3 | rule is `NO_LIMIT` | OK, 「{label} — 같은 계열을 반복해도 제한이 없는 계열입니다」 |
| 4 | `history` is empty | OK, 「살포 이력이 없습니다」 |
| 5 | `consecutive >= max_consecutive` | CAUTION, 「{label} — 직전까지 같은 계열을 연속 {consecutive}회 사용했습니다. 연속 {max_consecutive}회까지가 기준이라 같은 작용기작이 반복됩니다」 |
| 6 | `consecutive == 0` | OK, 「{label} — 직전 살포는 다른 계열입니다」 |
| 7 | otherwise | OK, 「{label} — 직전까지 같은 계열을 연속 {consecutive}회 사용했습니다 (연속 {max_consecutive}회까지 기준)」 |

- `label` = `moa.label_kr`, plus ` ({system} {code})` when both exist (「가1 (FRAC 4)」). The same helper labels `facts.label` and each `window[].label` (None for a record without `moa`).
- Recent-first order: `sprayed_on` descending, then `id` descending. `consecutive` = leading records whose `moa` is not None and has the same `label_kr` as the chosen drug; anything else, including a record without `moa`, stops the count. `window` = first 3 of that order; `unknown` = records in `window` without `moa`. For #3–#7 (and #2) these are computed from the history whatever the confirmation; for #1 every number is None and `window` is `[]`.
- Messages of #3, #5, #6, #7 end with ` (작용기작 미상 {unknown}건 포함)` when `unknown >= 1`.
- `evidence.source_text` = the applied rule's `source`; 「없음」 for #1.

### Rule table (`rotation_rule(moa) -> RotationRule`)

Decided from `label_kr`; compound labels (`+`) are split and each part is looked up without `system` (an unknown `system` means 「그 밖의 계열」). First match wins:

| Group | kind | `max_consecutive` | `source` (copied from `rotation_rule.json`) |
|---|---|---|---|
| `카` | NO_LIMIT | None | FRAC Multi-site Guidelines |
| `8a`–`8f`, `13`, `미분류(살충제)` | NO_LIMIT | None | IRAC 예외 그룹 |
| `가1` | CONSECUTIVE | 2 | FRAC Phenylamides (last updated March 2020) |
| `아5` | CONSECUTIVE | 2 | FRAC CAA WG 2026 회의록 3.2절 |
| any other with `system == "IRAC"` | CONSECUTIVE | 2 | IRAC MoA Classification v11.5 (Feb 2026) |
| everything else (incl. `생1`, `생2`, `미분류(살균제)`, `미분류`, no `system`) | CONSECUTIVE | 1 | 농식품부 PLS 안내 |

Compound: the result is NO_LIMIT only if every part is; otherwise the smallest `max_consecutive`, and the first part with that value gives the `source`.

## Calls I made (please check)

1. **NO_LIMIT labels** are `카`, `8a`–`8f`, `13` and `미분류(살충제)`. The delivered data has three 미분류 groups; the table's 「미분류(IRAC UN)」 is the insecticide one, while `미분류(살균제)` and the plain `미분류` (a fungicide, "FRAC 성분별") fall under 「그 밖의 계열」. This matches the data owner's multi-site flag for all of them except 생1 and 생2, which you decided to leave out.
2. **Sources** use the exact strings of `rotation_rule.json` (more specific than the table in the rules, and M3 expects 「FRAC Phenylamides (last updated March 2020)」). A test keeps the hard-coded table equal to the JSON.
3. **`used` is None when ③ cannot count** (NEEDS_CHECK, NO_LIMIT), as is every ③ number that depends on it. The spec's `used: int` is read together with its rule "값이 없으면 null이다".
4. **④ facts for `moa` None** are all None with an empty `window`; for the other cases the numbers are computed from the history, also when the confirmation is missing.
5. **`label` in ④ facts and `window[].label`** use the display form 「가1 (FRAC 4)」.
6. ③ uses the same `calc_rows` as ② (judgment rules §3), so an `AT_PLANTING` row is dropped when other rows exist and decides alone otherwise (C19).
7. Test files `tests/test_judge_count.py`, `tests/test_judge_moa.py`, `tests/test_judge_rotation_rule.py`; the existing message-scan test in `tests/test_judge_domain_rules.py` is extended to ③④ (MSG1).

## Additions to the §9 tables

- Boundary: a spray on `planted_at` itself counts; one day before does not.
- Another item's records and records with the same item under another brand are told apart by `item_name` only (C7, C8 already).
- ④ with a history where the first (newest) record is the chosen group but older ones are not: `consecutive = 1`.
- Rule table: every group above, 생1/생2 → 1, 미분류 variants, compound with an unknown part, and all 70 `moa.json` labels get a rule without error.

## Left to the builder

Helper names beyond those in this document, how the rule table is stored (a dict of labels or small functions), and the shared test builders for `SprayRecord`.

## Open questions (not blocking)

- 「시즌 최대」 / 30-day window of `rotation_rule.json` (judgment rules §10-9), and whether 생1/생2 should later be NO_LIMIT; one more table line is enough to change that.
