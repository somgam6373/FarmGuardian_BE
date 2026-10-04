# 팜가디언 `judge()` 판정 규칙

- 작성일: 2026-10-04
- 기준 문서: `farmguardian_flow_spec.md` §3, `docs/dev/farmguardian_architecture.md` §6
- 이 문서는 **판정 규칙에 한해** 위 두 문서보다 우선한다. 충돌하면 이 문서를 따르고 상대 문서를 고친다.
- 용도: 팀장은 이 문서대로 `judge/rules.py`를 구현하고, 팀원은 §9의 케이스 표를 `pytest.mark.parametrize`로 옮긴다.

## 1. 확정 결정 요약

| 항목 | 결정 |
|---|---|
| ② 시기 | 수확 예정일을 입력받지 않는다. **"오늘 살포하면 N월 N일부터 수확 가능"을 계산해 표시**한다. ②는 `BLOCKED`를 내지 않는다 |
| ③ 집계 단위 | **품목명(`item_name`) 기준 합산.** 같은 품목의 다른 상표 이력도 같은 약으로 센다. 성분 단위 합산은 미확인 (§10-1) |
| ③ 횟수 창 | 일년생 = `planted_at` 이후, 다년생 = 올해 1/1 이후 (KST). "N회 이내" = 최대 N회까지 허용 |
| ③ 마지막 1회 | 판정은 `OK`, `message`로만 알린다. `CAUTION` 없음 |
| ④ 창과 임계값 | 구역 이력 **최근 3건** 중 고른 약제와 같은 작용기작이 **2건 이상**이면 `CAUTION`. 고른 약제는 창에 넣지 않는다 |
| ④ 성격 | 효과 문제. `BLOCKED` 없음 |
| `moa` NULL | 고른 약제의 `moa`가 NULL이면 ④ = `NEEDS_CHECK`. 샘플 조사 후 재검토 |
| 병해충 미지목 | 고려 대상 행 전체의 가장 엄격한 값 (PHI 최대, 횟수 최소) + 안내 문구. 대안은 계산하지 않음 |
| 편중도(`rotation`) | 작기 전체 비율. ④ 판정과 별개 함수 |
| 대안 | 같은 작물×병해충의 다른 약제 중 `OK`이고 작용기작이 다른 것. 상세는 §7 |
| 문구 | 백엔드가 생성한다. 예측·추천·확률·"안전" 표현 금지 (§8) |

## 2. 타입

`judge/schemas.py` (Pydantic). 이 모듈과 `judge/rules.py`는 DB·HTTP를 임포트하지 않는다.

```python
class Verdict(str, Enum):        # 가능 / 주의 / 불가 / 확인 필요
    OK, CAUTION, BLOCKED, NEEDS_CHECK
PRIORITY = {BLOCKED: 3, NEEDS_CHECK: 2, CAUTION: 1, OK: 0}

class Moa:           label_kr, system: str | None, code: str | None
                     # label_kr = PSIS indictSymbl (예: "라3"). system/code = FRAC·IRAC (예: FRAC / 4)

class Registration:                  # 고른 상표(pesticide_id)의 이 작물에 대한 PSIS 행
    pest_id: int
    pest_name: str
    phi_days: int | None             # use_suittime_raw 파싱 결과
    max_uses: int | None             # use_num_raw 파싱 결과
    use_suittime_raw: str | None     # 예: "수확 14일 전까지"
    use_num_raw: str | None          # 예: "5회 이내"
    dilut_raw: str | None
    use_timing_raw: str | None
    data_asof: date                  # 적재일 (PSIS가 갱신일을 주지 않음)

class SprayRecord:
    id: int
    pesticide_id: int
    item_name: str
    sprayed_on: date
    moa: Moa | None

class JudgeInput:
    today: date                      # 주입. 시계 없이 테스트한다. KST 기준
    is_perennial: bool
    planted_at: date
    no_prior_spray: bool
    pest_id: int | None              # None = 병해충 미지목
    pesticide_id: int
    item_name: str
    moa: Moa | None
    registrations: list[Registration]   # 고른 상표의 이 작물 행 전부 (병해충 무관)
    history: list[SprayRecord]          # 구역 전체 이력

class Evidence:      source_text: str, data_asof: date
class CheckResult:   key, status: Verdict, message: str, facts: dict, evidence: Evidence | None
                     # key = registration | timing | count | moa

class JudgeResult:
    pesticide_id: int
    moa: Moa | None
    verdict: Verdict                 # checks 중 PRIORITY 최고값
    checks: list[CheckResult]        # 항상 4개, 순서 registration, timing, count, moa
    notices: list[str]
    data_asof: date | None           # 고려한 행들의 data_asof 중 가장 오래된 값. 화면 표기는 "데이터 조회일"

class RotationItem:    moa: Moa | None, count: int       # None = 작용기작 미상
class RotationSummary: window_start: date, total: int, items: list[RotationItem]

def judge(inp: JudgeInput) -> JudgeResult
def window_start(today, is_perennial, planted_at) -> date
def rotation_summary(history, today, is_perennial, planted_at) -> RotationSummary
def pick_alternatives(selected: JudgeResult, others: list[JudgeResult]) -> list[JudgeResult]
```

`Alternative`(`pesticide_id, name, item_name, moa`)은 서비스가 `pick_alternatives` 결과에 이름을 채워 만든다.

## 3. 공통 규칙

**고려 대상 행(`rows`).**
- `pest_id`가 있으면 `registrations` 중 `pest_id`가 같은 행.
- `pest_id`가 None이면 `registrations` 전부.
- 같은 대상에 행이 여럿이면 ②는 `phi_days` 최댓값, ③은 `max_uses` 최솟값 (가장 엄격한 값).
- **고려 대상 행 중 하나라도 해당 값이 NULL이면 그 체크는 `NEEDS_CHECK`.** 읽지 못한 행이 더 엄격할 수 있기 때문이다 (보수적 선택). 원문은 NULL인 행의 것을 보여준다.

**`window_start`.** 일년생 `planted_at`, 다년생 `date(today.year, 1, 1)`.

**날짜 표기(`message`).** `today`와 같은 해면 「10월 11일」, 다른 해면 「2027년 1월 8일」. `facts`와 `Evidence`의 날짜는 ISO 문자열.

## 4. 체크별 규칙

판정 순서는 위에서 아래로 첫 번째로 맞는 줄에서 멈춘다.

### ① registration (등록)

| 조건 | status | facts |
|---|---|---|
| `registrations`가 비어 있음 | `BLOCKED` (작물 미등록) | `{crop_registered: false}` |
| `pest_id` 있음, `rows`가 비어 있음 | `BLOCKED` (다른 병해충에만 등록) | `{crop_registered: true, registered_pests: [이름…]}` |
| 그 외 | `OK` | `{pest_specified: bool, rows: n}` |

`evidence.source_text` = `use_timing_raw`와 `dilut_raw` 중 값이 있는 것을 " · "로 연결 (예: 「발생초기 경엽처리 · 1000배」). 둘 다 없으면 `evidence = None`.

### ② timing (시기)

| 조건 | status |
|---|---|
| ①이 `BLOCKED` | `NEEDS_CHECK` (등록 정보 없음) |
| `rows` 중 `phi_days` NULL이 있음 | `NEEDS_CHECK` (원문 표시) |
| `phi = max(phi_days)` = 0 | `OK` (수확 당일까지) |
| `phi` ≥ 1 | `OK` |

`facts = {phi_days, harvest_from, rows}`, `harvest_from = today + phi`. `evidence.source_text` = 가장 엄격한 행의 `use_suittime_raw`. **`BLOCKED`는 내지 않는다.**

### ③ count (횟수)

| 조건 | status |
|---|---|
| ①이 `BLOCKED` | `NEEDS_CHECK` (등록 정보 없음) |
| `rows` 중 `max_uses` NULL이 있음 | `NEEDS_CHECK` (원문 표시) |
| `history`가 비어 있고 `no_prior_spray`가 false | `NEEDS_CHECK` (이력 없음) |
| `used >= max` | `BLOCKED` |
| 그 외 | `OK` |

- `max = min(max_uses)`.
- `used` = `history` 중 `item_name`이 같고 `sprayed_on >= window_start`인 건수. 같은 날 여러 건은 각각 1건. 이력이 있지만 창 안에 없으면 `used = 0` (확인 필요가 아님).
- 이번 살포는 `used + 1`번째. `used + 1 == max`이면 마지막 횟수 문구를 쓴다 (상태는 `OK`).
- `facts = {used, max_uses, since, item_name}`. `evidence.source_text` = 가장 엄격한 행의 `use_num_raw`.
- 앞쪽 조건이 먼저 걸리는 이유: 사용자가 고칠 수 없는 원인(등록·기준 읽기 실패)을 먼저 보여준다.

### ④ moa (작용기작)

| 조건 | status |
|---|---|
| 고른 약제 `moa`가 None | `NEEDS_CHECK` |
| `history`가 비어 있고 `no_prior_spray`가 false | `NEEDS_CHECK` (이력 없음) |
| `history`가 비어 있고 `no_prior_spray`가 true | `OK` (0/0) |
| `hits >= 2` | `CAUTION` |
| 그 외 | `OK` |

- 창 = `history`를 `sprayed_on` 내림차순, 같은 날이면 `id` 내림차순으로 정렬한 **앞 3건** (3건 미만이면 있는 만큼). 작기와 무관하다.
- `of = len(창)`, `hits` = 창에서 `moa.label_kr`이 고른 약제와 같은 건수. `moa`가 None인 이력은 창에 포함하되 일치로 세지 않고 `unknown`으로 센다.
- ④는 ①의 결과와 무관하게 계산한다.
- `facts = {label, hits, of, unknown}`. `evidence = None`.

## 5. 최종 판정과 notices

- `verdict` = 4개 체크 `status` 중 `PRIORITY`가 가장 높은 값.
- `notices`: `pest_id`가 None이고 `registrations`가 비어 있지 않으면 「병해충을 지정하지 않아 가장 엄격한 기준을 적용했습니다」 한 줄.
- `data_asof` = 고려한 `rows`의 `data_asof` 중 최솟값. `rows`가 없으면 None.
- 서비스가 `pest_id`가 None이고 `verdict`가 `BLOCKED`/`CAUTION`이면 `notices`에 「병해충을 지정하면 대안을 볼 수 있습니다」를 추가한다.

## 6. 편중도 (`rotation_summary`)

- 창 = `window_start(...)` 이후 `history` 전체. 약제 수와 무관하게 **살포 건수**로 센다.
- 작용기작별(`moa.label_kr`)로 묶어 `count`를 센다. `moa`가 None인 건은 `moa: None` 항목 하나로 센다.
- 정렬: `count` 내림차순, 같으면 `label_kr` 오름차순, `None` 항목은 맨 뒤.
- `total` = 창 안의 전체 건수. 이력이 없으면 `total = 0`, `items = []`. 비율은 프론트가 `count / total`로 계산한다.
- ④ 판정(최근 3건 창)과 별개다. 두 함수가 서로의 결과를 쓰지 않는다.

## 7. 대안

`pick_alternatives(selected, others)` (순수). `others`는 같은 작물×병해충의 다른 약제들을 각각 `judge()`로 돌린 결과.

1. `verdict == OK`인 것만.
2. 대안 `moa`가 None이면 제외.
3. 고른 약제 `moa`가 있으면 대안 `moa.label_kr`이 달라야 한다. 고른 약제 `moa`가 None이면 이 비교만 생략한다.
4. 같은 품목의 다른 상표는 `moa`가 같으므로 3번에서 자동으로 빠진다.

서비스 규칙:
- 후보 풀 = 같은 작물 × **같은 병해충**에 등록된 약제 (고른 약제 제외). DB 조회는 후보마다가 아니라 **한 번에 묶어서** 한다.
- 병해충 미지목이면 대안을 계산하지 않는다.
- 정렬: `moa.label_kr` → `item_name` → `name`. PHI·이름 외 기준(짧은 순 등)은 추천처럼 보이므로 쓰지 않는다. 서버 상한 없음.
- `show_extension_office = true` 조건: 병해충을 지목했고, `verdict`가 `BLOCKED` 또는 `CAUTION`이며, 대안이 0건일 때만.

## 8. 문구

**작성 규칙:** 존댓말, 사실만 서술한다. 예측·추천·확률·"안전하다"는 뜻의 표현은 쓰지 않는다. **금지어 테스트 대상: `추천 예측 예상 가능성 위험 확률 안전 문제없`.** ("수확 가능"은 계산 결과라 허용, "가능성"만 금지.)

| 체크 | 상태 | 조건 | message |
|---|---|---|---|
| ① 등록 | OK | 병해충 지목 | 이 병해충에 등록된 약제입니다 |
| | OK | 병해충 미지목 | 이 작물에 등록된 약제입니다 (병해충 미지정) |
| | BLOCKED | 다른 병해충에만 등록 | 이 병해충에는 등록되어 있지 않습니다 (이 작물에 등록된 병해충 {n}종) |
| | BLOCKED | 작물에 등록 없음 | 이 작물에는 등록되어 있지 않습니다 |
| ② 시기 | OK | `phi_days` ≥ 1 | 오늘 살포하면 {harvest_from}부터 수확할 수 있습니다 (수확 {phi}일 전까지 사용) |
| | OK | `phi_days` = 0 | 수확 당일까지 사용할 수 있습니다 |
| | NEEDS_CHECK | `phi_days` NULL | 수확 전 사용 기준을 읽지 못했습니다. 원문: {raw} |
| | NEEDS_CHECK | ①이 BLOCKED | 등록 정보가 없어 확인할 수 없습니다 |
| ③ 횟수 | OK | `used + 1 < max` | 이번이 {n}회째입니다 (최대 {max}회) |
| | OK | `used + 1 == max` | 이번이 {max}회째로 마지막 사용 가능 횟수입니다 (최대 {max}회) |
| | BLOCKED | `used >= max` | {since}부터 {used}회 사용해 최대 {max}회를 채웠습니다 |
| | NEEDS_CHECK | 이력 0건 + 「뿌린 적 없음」 미선택 | 살포 이력이 없어 확인할 수 없습니다. 이력을 입력하거나 「뿌린 적 없음」을 선택해 주세요 |
| | NEEDS_CHECK | `max_uses` NULL | 최대 사용 횟수 기준을 읽지 못했습니다. 원문: {raw} |
| | NEEDS_CHECK | ①이 BLOCKED | 등록 정보가 없어 확인할 수 없습니다 |
| ④ 작용기작 | OK | `hits` < 2 | {label} — 최근 {of}회 중 {hits}회 |
| | OK | 이력 0건 + 「뿌린 적 없음」 | 살포 이력이 없습니다 |
| | CAUTION | `hits` ≥ 2 | {label} — 최근 {of}회 중 {hits}회. 같은 작용기작이 반복되고 있습니다 |
| | NEEDS_CHECK | 이력 0건 + 미선택 | 살포 이력이 없어 확인할 수 없습니다. 이력을 입력하거나 「뿌린 적 없음」을 선택해 주세요 |
| | NEEDS_CHECK | 고른 약제 `moa` NULL | 이 약제의 작용기작 정보가 없어 비교할 수 없습니다 |

- `{n}` = `registered_pests`의 개수, `{n}`(③) = `used + 1`.
- `{label}`은 `moa.label_kr`, `system`과 `code`가 있으면 「가1 (FRAC 4)」.
- ④에서 `unknown ≥ 1`이면 `message` 끝에 「 (작용기작 미상 {unknown}건 포함)」을 붙인다.
- `{raw}`는 NULL인 행의 원문. 원문 자체가 비어 있으면 「없음」.

**범위 밖(프론트 고정 문구):** 「횟수는 정식일(다년생은 올해 1월 1일) 이후 기준으로 집계합니다」, 그리고 "가능"이 사용 보증으로 읽히지 않게 하는 **면책 한 줄**. 면책 문구는 제품·법무와 정한다 (§10-4).

## 9. 테스트 케이스 표

기준 픽스처 `base`: `today = 2026-10-04`, 일년생, `planted_at = 2026-05-01`, `no_prior_spray = false`, `pest_id = 1`(탄저병), 고른 약제 = 상표 10 / 품목 「품목A」 / `moa` 「가1」, `registrations = [pest 1, phi 7, max 3, use_suittime_raw "수확 7일 전까지", use_num_raw "3회 이내", dilut "1000배", timing "발생초기 경엽처리", data_asof 2026-10-01]`, `history = []`.

이력 표기: `품목A(가1)@2026-06-01` = 품목A, 작용기작 가1, 살포일. 기재 없는 항목은 `base` 그대로. **판정에 영향이 없는 체크는 비교하지 않는다.**

### 등록 ①
| ID | 입력 변경 | 기대 |
|---|---|---|
| R1 | `history = [품목B(나2)@06-01]` | ① `OK`, 「이 병해충에 등록된 약제입니다」, evidence 「발생초기 경엽처리 · 1000배」 |
| R2 | `registrations = [pest 2 "역병" 1행]` | ① `BLOCKED`, 「이 병해충에는 등록되어 있지 않습니다 (이 작물에 등록된 병해충 1종)」, `facts.registered_pests = ["역병"]`. ②③ `NEEDS_CHECK` 「등록 정보가 없어 확인할 수 없습니다」. `verdict = BLOCKED` |
| R3 | `registrations = []` | ① `BLOCKED`, 「이 작물에는 등록되어 있지 않습니다」, `data_asof = None` |
| R4 | `pest_id = None` | ① `OK`, 「이 작물에 등록된 약제입니다 (병해충 미지정)」, `notices = ["병해충을 지정하지 않아 가장 엄격한 기준을 적용했습니다"]` |
| R5 | `pest_id = None`, `registrations = []` | ① `BLOCKED`, `notices = []` |

### 시기 ②
| ID | 입력 변경 | 기대 |
|---|---|---|
| T1 | (`history`는 R1과 같게) | ② `OK`, `harvest_from = 2026-10-11`, 「오늘 살포하면 10월 11일부터 수확할 수 있습니다 (수확 7일 전까지 사용)」 |
| T2 | `phi_days = 0` | ② `OK`, 「수확 당일까지 사용할 수 있습니다」, `harvest_from = 2026-10-04` |
| T3 | `phi_days = None`, `use_suittime_raw = "수확 직전"` | ② `NEEDS_CHECK`, 「수확 전 사용 기준을 읽지 못했습니다. 원문: 수확 직전」 |
| T4 | `pest_id = None`, 행 = pest 1(phi 7), pest 2(phi 14) | `phi_days = 14`, `harvest_from = 2026-10-18` |
| T5 | 행 = pest 1(phi 7), pest 1(phi 10), pest 2(phi 30) | `phi_days = 10` (pest 2 행은 무시) |
| T6 | 행 = pest 1(phi 7), pest 1(phi None) | ② `NEEDS_CHECK` |
| T7 | `today = 2026-12-25`, `phi_days = 14` | 「오늘 살포하면 2027년 1월 8일부터 수확할 수 있습니다 (수확 14일 전까지 사용)」 |

### 횟수 ③
| ID | 입력 변경 | 기대 |
|---|---|---|
| C1 | `history = [품목B(나2)@06-01]` | `used = 0`, `OK`, 「이번이 1회째입니다 (최대 3회)」 |
| C2 | `history = [품목A(가1)@06-01]` | `used = 1`, 「이번이 2회째입니다 (최대 3회)」 |
| C3 | `history = [품목A@06-01, 품목A@06-15]` | `used = 2`, 「이번이 3회째로 마지막 사용 가능 횟수입니다 (최대 3회)」, 상태 `OK` |
| C4 | `history = [품목A@06-01, 06-15, 07-01]` | `used = 3`, `BLOCKED`, 「5월 1일부터 3회 사용해 최대 3회를 채웠습니다」 |
| C5 | `history = [품목A@2026-04-20, 품목A@2026-06-01]` | `used = 1` (정식일 이전 이력 제외) |
| C6 | `is_perennial = true`, `planted_at = 2024-03-01`, `history = [품목A@2025-12-31, 품목A@2026-01-01]` | `used = 1`, `since = 2026-01-01` |
| C7 | `history = [품목A(상표 10)@06-01, 품목A(상표 11)@06-10]` | `used = 2` (같은 품목은 상표가 달라도 합산) |
| C8 | `history = [품목B@06-01]` | `used = 0` |
| C9 | `history = []`, `no_prior_spray = false` | ③ `NEEDS_CHECK`, 「살포 이력이 없어 확인할 수 없습니다. …」 |
| C10 | `history = []`, `no_prior_spray = true` | `used = 0`, `OK`, 「이번이 1회째입니다 (최대 3회)」 |
| C11 | `max_uses = None`, `use_num_raw = "-"` | ③ `NEEDS_CHECK`, 「최대 사용 횟수 기준을 읽지 못했습니다. 원문: -」 |
| C12 | `history = [품목A@06-01, 품목A@06-01]` | `used = 2` (같은 날 2건은 각각 1회) |
| C13 | `pest_id = None`, 행 = pest 1(max 5), pest 2(max 3) | `max = 3` |
| C14 | `history = [품목A@2026-04-01]` | `used = 0`, `OK` (이력은 있으나 창 밖이라 확인 필요가 아님) |

### 작용기작 ④ (고른 약제 `moa` = 가1)
이력은 **최근순**으로 적는다.

| ID | 입력 변경 | 기대 |
|---|---|---|
| M1 | `history = []`, `no_prior_spray = true` | ④ `OK`, 「살포 이력이 없습니다」, `hits = 0, of = 0` |
| M2 | `history = []`, `no_prior_spray = false` | ④ `NEEDS_CHECK`, 「살포 이력이 없어 확인할 수 없습니다. …」 |
| M3 | `[품목B(가1)@09-01, 품목C(가1)@08-01, 품목D(나2)@07-01]` | `CAUTION`, 「가1 — 최근 3회 중 2회. 같은 작용기작이 반복되고 있습니다」 |
| M4 | `[품목B(가1), 품목D(나2), 품목E(다3)]` | `OK`, 「가1 — 최근 3회 중 1회」 |
| M5 | (a) `[가1, 나2]` / (b) `[가1, 가1]` | (a) `OK`, 「최근 2회 중 1회」 / (b) `CAUTION`, 「최근 2회 중 2회」 |
| M6 | 고른 약제 `moa = None` (이력은 무관) | ④ `NEEDS_CHECK`, 「이 약제의 작용기작 정보가 없어 비교할 수 없습니다」 |
| M7 | `[미상, 가1, 미상]` | `OK`, 「가1 — 최근 3회 중 1회 (작용기작 미상 2건 포함)」 |
| M8 | `[나2, 다3, 라4, 가1]` (가1이 가장 오래됨) | 창 = 앞 3건, `hits = 0`, `OK`, 「가1 — 최근 3회 중 0회」 |
| M9 | 같은 날(09-01) 이력 `id 4(가1), id 5(가1), id 6(나2)` + 08-30 `id 3(가1)` | 창 = id 6, 5, 4. `hits = 2`, `CAUTION` (id 3은 창 밖) |
| M10 | `moa = (가1, FRAC, 4)` | message 앞부분이 「가1 (FRAC 4) — …」 |

### 최종 판정 · 기타
| ID | 입력 | 기대 |
|---|---|---|
| V1 | ① `BLOCKED` + ④ `CAUTION` | `verdict = BLOCKED` |
| V2 | ③ `NEEDS_CHECK` + ④ `CAUTION` | `verdict = NEEDS_CHECK` |
| V3 | ④ `CAUTION`, 나머지 `OK` | `verdict = CAUTION` |
| V4 | 모두 `OK` | `verdict = OK`, `checks`는 4개, 순서 registration, timing, count, moa |
| V5 | 행 `data_asof`가 2026-10-01, 2026-09-20 | `data_asof = 2026-09-20` |
| RT1 | `planted_at = 2026-05-01`, 이력: 가1 4건(정식일 이후) + 가1 1건(정식일 이전) + 나2 2건 + 미상 1건 | `window_start = 2026-05-01`, `total = 7`, `items = [가1:4, 나2:2, None:1]` |
| RT2 | `history = []` | `total = 0`, `items = []` |
| A1 | 다른 약제 `OK`, `moa` 나2 | 대안에 포함 |
| A2 | 다른 약제 `OK`, `moa` 가1 (같은 품목 다른 상표) | 제외 |
| A3 | 다른 약제 `CAUTION` / `BLOCKED` / `NEEDS_CHECK` | 제외 |
| A4 | 다른 약제 `OK`, `moa = None` | 제외 |
| A5 | 고른 약제 `moa = None`, 다른 약제 `OK` + `moa` 있음 | 포함 (`moa` 비교 생략) |
| S1 | 서비스: 병해충 지목, `BLOCKED`, 대안 0건 | `show_extension_office = true` |
| S2 | 서비스: 병해충 미지목, `BLOCKED` | `show_extension_office = false`, `notices`에 「병해충을 지정하면 대안을 볼 수 있습니다」 |
| MSG1 | §8 템플릿 전체 | 금지어(`추천 예측 예상 가능성 위험 확률 안전 문제없`)가 하나도 없음 |

## 10. 미결·확인 사항

1. **성분 단위 합산 여부.** 법령·PSIS 기준이 품목 단위인지 성분 단위인지 확인되지 않았다. 성분 합산이 맞으면 품목 기준은 횟수를 적게 세어 **"가능"이 잘못 나온다** (위험한 쪽 오류). **출시 전에 농업기술센터·PSIS 문서로 확인한다.** PSIS 목록의 `engName`(주성분 일반명, 예 `kasugamycin SL2.3 %`)으로 성분 키를 만들 수 있으나 파싱이 지저분하다.
2. **다작용점 약제(만코제브, 구리제 등)를 ④에서 제외할지.** 저항성 위험이 낮다는 주장이 있으나 검증하지 못했다. 농학 전문가 확인 필요. MVP에서는 반영하지 않으며, 맞다면 이런 약제의 반복 살포에 ④가 내는 `CAUTION`은 오탐이다 (③ 횟수 제한은 그대로 적용).
3. **PSIS 샘플 조사 (S1 월요일).** 3개 작물로 실제 호출해 확인한다.
   - `indictSymbl`이 비거나 "-"인 비율, 혼합제 표기, 용도가 다른 약제 사이의 기호 충돌 → `moa` NULL 처리 재검토
   - `useSuittime`/`useNum` 문자열 변형과 파싱 실패율, 목록 응답에 두 필드가 실제로 포함되는지
   - 같은 (작물, 병해충, 품목)에 행이 여럿인 경우, `diseaseUseSeq`의 범위
   - `useName` 값 종류 (제초제·생장조정제를 적재 범위에서 뺄지)
   - 작물명 변형 ("고추" vs "고추(풋고추)" 등)
   - 작물×병해충당 약제 수 (대안 목록 길이 가정 확인)
4. **면책 문구.** "가능"이 사용 보증으로 읽히지 않게 하는 문구를 제품·법무와 정한다.
5. **별표 8 매핑표.** 한글 작용기작 기호 → FRAC·IRAC 코드. 누가 언제 만드는지 확인하고 `moa.system/code` 시드로 쓴다.
6. **"읽지 못한 행이 하나라도 있으면 `NEEDS_CHECK`" 규칙(§3)의 영향.** 파싱 실패율이 높으면 `NEEDS_CHECK`가 너무 자주 뜬다. 샘플 조사 결과를 보고 재검토한다.
