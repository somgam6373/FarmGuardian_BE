# Rotation summary and alternatives — BE-43 / BE-44 (design)

- Date: 2026-10-29
- Owner: Junhyeok (judgment context)
- Status: draft, waiting for approval
- Basis: **`팜가디언_API_명세.md` (the frame, unchanged)** §2 (`Rotation`, `Alternative`, `JudgeResponse`), §5 (`GET /zones/{id}`), §7; `팜가디언_판정_규칙.md` §2, §6, §7, §9 (RT1–RT3, A1–A5); `2026-10-29-judge-final-design.md`

## The API spec is the frame

`팜가디언_API_명세.md` does not change and nothing here edits it.

- `rotation_summary` returns exactly the spec's `Rotation {window_start: date|null, total: int, items: [{moa: Moa|null, count: int}]}`. It is the `rotation` field of `GET /zones/{id}`; the frontend computes ratios as `count / total`.
- `pick_alternatives` returns `JudgeResult`s. The spec's `Alternative {id, name, item_name, moa}` is built by the service from them (names are not in `JudgeResult`), so no `Alternative` type is added to the domain.
- Dates serialize as ISO strings; `moa` as `{label_kr, system, code}` or null.

## Intent

Two small pure functions that finish the judgment domain: how the spray history is spread over action groups in the current season (the chart on the zone screen), and which other drugs can be offered instead of a blocked or cautioned one.

## Goals

- `RotationItem`, `RotationSummary` in `judgment/domain/schemas.py`; `rotation_summary(history, planted_at)` and `pick_alternatives(selected, others)` in `rules.py`.
- Tests: RT1–RT3 and A1–A5 of judgment rules §9, plus the additions below.

## Non-goals (other tasks)

- The candidate pool (other drugs registered for the same crop and pest, fetched in one query), running `judge()` for each candidate, sorting by `moa.label_kr` → `item_name` → `name`, filling names into `Alternative`, `show_extension_office` (judgment rules §7 "서비스 규칙", cases S1–S3), the extra notice 「병해충을 지정하면 대안을 볼 수 있습니다」, `GET /zones/{id}` itself: all BE-45.
- ④ (`check_moa`) and `rotation_summary` stay independent: neither uses the other's result (judgment rules §6).

## `rotation_summary(history, planted_at) -> RotationSummary`

- Window: records with `sprayed_on >= planted_at`; with `planted_at` None the whole history and `window_start = None`. `window_start` is `planted_at`.
- Counted by spray records, not by drugs: one record = 1, whatever the drug.
- Grouped by `moa.label_kr`; records without `moa` form one item with `moa = None`.
- Order: `count` descending, then `label_kr` ascending, the `None` item last.
- `total` = records in the window; no records → `total = 0`, `items = []`.
- Independent of `history_confirmed` (it shows the records that exist).

## `pick_alternatives(selected, others) -> list[JudgeResult]`

`others` are the `judge()` results of the other drugs for the same crop and pest. Keep an item only if (judgment rules §7):

1. its `verdict` is `OK`;
2. its `moa` is not None;
3. when `selected.moa` is not None, its `moa.label_kr` differs from `selected.moa.label_kr` (when `selected.moa` is None this comparison is skipped).

Same-item drugs of another brand share the action group, so rule 3 removes them. The function only filters: the input order and the objects are kept; sorting and names belong to the service.

## Calls I made (please check)

1. **Window boundary:** `sprayed_on >= planted_at`, the same as ③ ("정식일 이후" in the rules does not say whether the day itself counts).
2. **One item per `label_kr`.** Records with the same label but different `system`/`code` are merged; the item's `moa` is the one of the newest record (`sprayed_on` descending, then `id` descending, as in ④).
3. **Alternatives compare `label_kr` only**, like ④ does.
4. `pick_alternatives` returns the given `JudgeResult` objects unchanged and in the given order.
5. `show_extension_office` is left to the service with the other S-cases, because it needs the service's alternative count and the pest choice.
6. Test files `tests/test_judge_rotation_summary.py` and `tests/test_judge_alternatives.py`, using `spray` / `recent` from `tests/judge_support.py` and a small `JudgeResult` builder in the alternatives test.

## Tests

- **Rotation:** RT1 (planted 2026-05-01; 가1 four after and one before, 나2 two, 미상 one → `window_start` 2026-05-01, `total` 7, `[가1:4, 나2:2, None:1]`); RT2 (no history); RT3 (no planting date: whole history, `window_start` None, `[가1:2, 나2:1]`).
  Additions: a record on `planted_at` counts and the day before does not; history only before `planted_at` → `total 0`, `items []`; ties on `count` ordered by `label_kr`; `None` last even with the highest count; the same label with different `system`/`code` merges; the result serializes to the spec shape; the input list is not changed.
- **Alternatives:** A1 (OK, 나2 vs selected 가1 → kept); A2 (OK, 가1 → dropped); A3 (CAUTION / BLOCKED / NEEDS_CHECK → dropped); A4 (OK, `moa` None → dropped); A5 (selected `moa` None, other OK with `moa` → kept).
  Additions: same `label_kr` with another `system` → dropped; several kept items stay in input order and are the same objects; empty `others` → `[]`.

## Left to the builder

Helper names, how the `JudgeResult` builder fills the four checks.

## Open questions (not blocking)

- None. Ordering of alternatives (`moa.label_kr` → `item_name` → `name`) is fixed by judgment rules §7 for BE-45.
