# Verdict screen wording and 「심을 때」 status (design)

- Date: 2026-11-04
- Owner: Hyebin (backend `app/judgment` messages, frontend `serverVerdict.ts`/`Verdict.tsx`)
- Status: draft, waiting for approval
- Repos: backend `FarmGuardian_BE` (PR to `test`), frontend `farmguardian-FE` (PR to `main`)

## Intent

A first-time user opening a drug's verdict screen (e.g. 엑사이도, 감자 가루더뎅이병) sees three problems:

1. A drug that is only used at planting (`at_planting_only`) shows 「확인 필요 · 자료가 없어 판단할 수 없어요」.
   The data is not missing; the drug is a planting-time drug. Decision #10 of
   `2026-11-02-frontend-integration-design.md` already says the frontend derives a 「심을 때」 status from
   `at_planting_only` and from an empty `planted_at`, but `serverVerdict.ts` never does it.
2. The headline and badges are frontend copy in 「~어요」, while every check sentence comes from the server in
   「~입니다」. One screen mixes both.
3. Three server sentences end with 「원문: 정식기」 glued onto the sentence, which reads oddly. The raw label text is
   useful and should stay visible, but on its own line.

Weather stays mock and unlabelled (decided by the user; not part of this work).

## Goals

1. A drug with `at_planting_only = true` shows the 「심을 때」 status with its own headline, and a zone without
   `planted_at` shows the 「심을 때」 status, both as decision #10 says. A ① `BLOCKED` still wins (불가 > 심을 때).
2. Every judgment `message` and `notices` sentence from the server uses 「~어요」 endings.
3. Server messages no longer contain 「원문: …」. The frontend shows the raw text (`evidence.source_text`) as a separate
   small grey line, in exactly the cases where it is shown today.
4. A test fails if a 「~니다」 ending comes back into a judgment template.

## Non-goals

- Changing any verdict status or rule (the only API change is the additive `facts.reason`). The server's statuses
  stay as they are (`AT_PLANTING` timing stays
  `NEEDS_CHECK`, the last remaining use stays `OK`, no history stays `OK`).
- Rewording beyond the sentence ending. Vocabulary (약제, 작용기작, 정식일, 살포) stays; only 「~입니다/습니다/
  됩니다」 endings become 「~예요/이에요/어요」.
- API error messages (`AppError` such as 「약제를 찾을 수 없습니다」, the `apply_date` 422). They are not verdict copy.
- Removing the duplicate sentence between the verdict hero reason and the check card (not requested).
- Weather.
- Rewriting stored judgments. Rows already saved keep their old text.

## Backend: message changes

Files: `app/judgment/domain/rules.py`, `app/judgment/application/service.py` (only `NO_ALTERNATIVE_NOTICE`).
The status, `facts` and `evidence` of every check stay the same; only `message`/notice strings change.

| Where | Now | New |
|---|---|---|
| ① OK | 이 병해충에 등록된 약제입니다 | 이 병해충에 등록된 약제예요 |
| ① NEEDS_CHECK | 병해충을 지정하지 않아 등록 여부를 확인할 수 없습니다 (이 작물에는 등록되어 있습니다) | 병해충을 지정하지 않아 등록 여부를 확인할 수 없어요 (이 작물에는 등록되어 있어요) |
| ① BLOCKED | 이 병해충에는 등록되어 있지 않습니다 (이 작물에 등록된 병해충 {n}종) | 이 병해충에는 등록되어 있지 않아요 (이 작물에 등록된 병해충 {n}종) |
| ① BLOCKED | 이 작물에는 등록되어 있지 않습니다 | 이 작물에는 등록되어 있지 않아요 |
| ② OK | 오늘 살포하면 {d}부터 수확할 수 있습니다 (수확 {phi}일 전까지 사용) | 오늘 살포하면 {d}부터 수확할 수 있어요 (수확 {phi}일 전까지 사용) |
| ② OK | 수확 당일까지 사용할 수 있습니다 | 수확 당일까지 사용할 수 있어요 |
| ② OK `NO_LIMIT` | 수확 전 사용 일수 제한이 없는 약제입니다. 라벨의 사용 방법을 확인해 주세요 | 수확 전 사용 일수 제한이 없는 약제예요. 라벨의 사용 방법을 확인해 주세요 |
| ② NEEDS_CHECK `AT_PLANTING` | 이 약은 심을 때(정식기·파종기) 쓰는 약입니다. 수확 전 사용 기준이 없어 수확 가능일을 계산할 수 없습니다. 원문: {raw} | 이 약은 심을 때(정식기·파종기) 쓰는 약이에요. 수확 전 사용 기준이 없어 수확 가능일을 계산할 수 없어요 |
| ② NEEDS_CHECK `phi` NULL | 수확 전 사용 기준을 읽지 못했습니다. 원문: {raw} | 수확 전 사용 기준을 읽지 못했어요 |
| ②③ NEEDS_CHECK ① BLOCKED | 등록 정보가 없어 확인할 수 없습니다 | 등록 정보가 없어 확인할 수 없어요 |
| ② BLOCKED | 수확 예정일({due})이 지났습니다 | 수확 예정일({due})이 지났어요 |
| ② BLOCKED | 수확 예정일({due})까지 {left}일 남아 수확 {phi}일 전까지 사용하는 기준을 지킬 수 없습니다 | …기준을 지킬 수 없어요 |
| ② CAUTION | 수확 예정일({due})까지 여유가 {margin}일입니다 (수확 {phi}일 전까지 사용) | 수확 예정일({due})까지 여유가 {margin}일이에요 (수확 {phi}일 전까지 사용) |
| ③ OK | 남은 횟수 {r}회, 이번 사용 후 {r-1}회입니다 (최대 {max}회) | {used_text} (최대 {max}회). 이번에 쓰면 {r-1}회 남아요 |
| ③ OK | 남은 횟수 1회, 이번 사용 후 0회입니다 (최대 {max}회). 이번이 마지막 사용입니다 | {used_text} (최대 {max}회). 이번에 쓰면 더 쓸 수 없어요 |
| ③ OK `NO_LIMIT` | 사용 횟수 제한이 없는 약제입니다. 라벨의 사용 방법을 확인해 주세요 | 사용 횟수 제한이 없는 약제예요. 라벨의 사용 방법을 확인해 주세요 |
| ③ BLOCKED | {since}부터 {used}회 사용해 최대 {max}회를 채웠습니다. 남은 횟수는 0회입니다 | {since}부터 {used}회 썼어요. 최대 {max}회를 채웠어요 |
| ③ NEEDS_CHECK | 정식일이 없어 이번 작기 사용 횟수를 셀 수 없습니다. 정식일을 입력해 주세요 | 정식일이 없어 이번 작기 사용 횟수를 셀 수 없어요. 정식일을 입력해 주세요 |
| ③④ NEEDS_CHECK | 살포 기록에 빠진 것이 없는지 확인되지 않았습니다. 기록을 입력하고 「누락 없음」을 선택해 주세요 | 살포 기록에 빠진 것이 없는지 확인되지 않았어요. 기록을 입력하고 「누락 없음」을 선택해 주세요 |
| ③ NEEDS_CHECK `max` NULL | 최대 사용 횟수 기준을 읽지 못했습니다. 원문: {raw} | 최대 사용 횟수 기준을 읽지 못했어요 |
| ④ OK `NO_LIMIT` | {label} — 같은 계열을 반복해도 제한이 없는 계열입니다 | {label} — 같은 계열을 반복해도 제한이 없는 계열이에요 |
| ④ OK | 살포 이력이 없습니다 | 살포 이력이 없어요 |
| ④ OK | {label} — 직전 살포는 다른 계열입니다 | {label} — 직전 살포는 다른 계열이에요 |
| ④ OK | {label} — 직전까지 같은 계열을 연속 {c}회 사용했습니다 (연속 {m}회까지 기준) | {label} — 직전까지 같은 계열을 연속 {c}회 사용했어요 (연속 {m}회까지 기준) |
| ④ CAUTION | {label} — 직전까지 같은 계열을 연속 {c}회 사용했습니다. 연속 {m}회까지가 기준이라 같은 작용기작이 반복됩니다 | {label} — 직전까지 같은 계열을 연속 {c}회 사용했어요. 연속 {m}회까지가 기준이라 같은 작용기작이 반복돼요 |
| ④ NEEDS_CHECK | 이 약제의 작용기작 정보가 없어 비교할 수 없습니다 | 이 약제의 작용기작 정보가 없어 비교할 수 없어요 |
| notice | 병해충을 지정하지 않아 가장 엄격한 기준을 적용했습니다 | 병해충을 지정하지 않아 가장 엄격한 기준을 적용했어요 |
| notice | 병해충을 지정하면 대안을 볼 수 있습니다 | 병해충을 지정하면 대안을 볼 수 있어요 |

The three ③ rows were also reworded (not only the ending), approved by Hyebin on 2026-11-04 after the first build: `{used_text}` is 「아직 쓰지 않았어요」 when `used` is 0, else 「{used}회 썼어요」.

Suffixes 「 ({use_method} 기준)」 and 「 (작용기작 미상 {n}건 포함)」 stay as they are. The three 「원문」 cases keep
the same `evidence.source_text` (the raw text, or 「없음」), so nothing is lost.

### `facts.reason` for timing and count `NEEDS_CHECK`

The frontend cannot tell from status and facts alone why a timing or count check is `NEEDS_CHECK` (for example, the
no-planting-date and the unconfirmed-history branches of ③ also have `max_uses = null` and a real `source_text`).
Matching on message text would be fragile. So the timing and count checks get one **additive** facts key, set only
when the status is `NEEDS_CHECK` (otherwise absent):

| Check | Branch | `facts.reason` |
|---|---|---|
| ② timing | ① BLOCKED / no rows | `not_registered` |
| ② timing | all `AT_PLANTING` | `at_planting` |
| ② timing | `phi` NULL | `unreadable` |
| ③ count | ① BLOCKED / no rows | `not_registered` |
| ③ count | `max_uses` NULL | `unreadable` |
| ③ count | no `planted_at` | `no_planting` |
| ③ count | history not confirmed | `unconfirmed` |

No existing key changes, so this is backward compatible. `팜가디언_API_명세.md` (the timing/count facts row) and
`팜가디언_판정_규칙.md` list the new key.

Tests:
- Update every test that asserts one of these strings (`tests/test_judge_*.py`, `tests/test_judgment_*.py`).
- `tests/test_judgment_wording.py`: update the known-template assertion, and add a test that no Korean literal in
  `rules.py` and no notice constant in `service.py` ends a sentence with 「니다」 (error messages in `service.py` are
  excluded). The forbidden-word test keeps passing.

Docs: `팜가디언_판정_규칙.md` §8 message table and the §9 test-case table rows that quote messages (T3, T9, T12, C3,
C11, C19, M1 and any others found) are updated to the new text; the §8 note about `{raw}` changes to say the raw text
is carried only in `evidence.source_text`.

## Frontend

### 「심을 때」 status (`src/lib/serverVerdict.ts`)

`toVerdict(item, planted)` gets whether the zone has a `plantedAt` and reads `facts.reason` per check.

- Timing check with `facts.reason = "at_planting"` (this is what `at_planting_only` means for the chosen drug)
  becomes status `preplant` with the state label 「심을 때」 (not 「심기 전」). The verdict's overall status becomes
  `preplant` unless a check is `no`.
- Count check with `facts.reason = "no_planting"` becomes `preplant` with the existing state label 「심기 전」.
- Zone without `plantedAt`: every drug whose overall status is not `no` becomes `preplant`, including drugs whose
  count never reaches the `no_planting` branch (no count limit, unreadable limit). When no check itself is
  `preplant`, the hero reason is 「심은 날을 넣으면 따져 드려요.」. This case already has the right headline
  (「심은 뒤에 판정할 수 있어요」) and the 「심은 날 입력하기」 link.
- Both at once (an at-planting drug on a zone without a planting date): the drug wins. Headline
  「심을 때 쓰는 약이에요」, no 「심은 날 입력하기」 link, at-planting record note. The count card still shows
  「심기 전」.
- `at_planting_only` itself is not needed for the mapping (it lives at the top of a preview item but under `pesticide`
  in the judge response); `facts.reason` is the same signal per check.
- Priority stays 불가 > 심을 때 > 확인 필요 > 주의 > 가능, so the DrugList tally and grouping pick it up without
  extra code.

### Verdict screen (`src/screens/Verdict.tsx`, `src/lib/verdict.ts`)

- The `Verdict` gets an `atPlanting` flag (timing reason is `at_planting`). With it the hero shows 「심을 때 쓰는 약이에요」
  instead of 「심은 뒤에 판정할 수 있어요」, and the 「심은 날 입력하기」 link is hidden.
- A `Check` gets an optional `stateLabel` override (used for 「심을 때」) and an optional `source` (raw text).
- Recording stays blocked for `preplant` as today. For `at_planting_only` the note under the button reads
  「심을 때 쓰는 약은 여기서 기록할 수 없어요」 instead of 「심은 뒤에 기록할 수 있어요」.

### Raw text line

`ServerCheck` gets `evidence: { source_text: string }`. A check shows its raw text as a separate small grey line
「원문: {source_text}」 under the sentence when `facts.reason` is `at_planting` or `unreadable`. These are exactly
today's three 「원문」 cases (② at planting, ② unreadable, ③ unreadable). If `source_text` is 「없음」 the line
reads 「원문: 없음」, as today.

Style: smaller font and muted colour, on its own line inside `.check__text`.

## Rollout

Two PRs, one per repo. Merge order does not matter for correctness: with the old backend the raw text appears twice
(inside the sentence and on its own line) until the backend PR lands; with the old frontend the sentence simply has no
raw text. Merge both before the demo.

## Verification

- Backend: `pytest` and `ruff check .` pass; the new 「니다」 guard test fails on the old text and passes on the new.
- Frontend: `npx tsc --noEmit` passes (Hyebin runs it); manual check on the local stack: 엑사이도 on 감자밭 shows
  「심을 때 · 심을 때 쓰는 약이에요」, the timing card shows the sentence and a separate 「원문: 정식기」 line, every
  check sentence ends in 「~어요」, and a zone without a planting date shows 「심을 때 · 심은 뒤에 판정할 수 있어요」.

## Calls made by Claude (please check)

- Only sentence endings change; wording otherwise stays.
- The at-planting headline 「심을 때 쓰는 약이에요」, the 「심을 때」 state label on the timing card, and the record
  note 「심을 때 쓰는 약은 여기서 기록할 수 없어요」.
- The empty-`planted_at` half of decision #10 is included because it is the same missing mapping.
- Error messages are out of scope.
- An additive `facts.reason` on timing/count `NEEDS_CHECK` so the frontend does not match message text.
- When an at-planting drug meets a zone without a planting date, the drug's headline wins.
- The manual check uses 감자밭 as it is now: its count card shows a count sentence, not the no-planting-date one, so it has a planting date.
