# 팜가디언 `judge()` 판정 규칙

- 작성일: 2026-10-04, 개정 2026-10-11 (PRD 반영), **개정 2026-10-28 (엑셀 데이터 반영: 사용 방법별 규칙, 심을 때·제한 없음, ④ 반복 규칙)**
- 기준 문서: `PRD.md` §6, `farmguardian_flow_spec.md` §3, `docs/dev/farmguardian_architecture.md` §6
- 이 문서는 **판정 규칙에 한해** 위 설계 문서보다 우선한다. 충돌하면 이 문서를 따르고 상대 문서를 고친다. PRD와 다르게 정한 항목은 `farmguardian_prd_feedback.md`에 PRD 수정 제안으로 남겼다.
- 용도: 팀장은 이 문서대로 `judgment/domain/rules.py`를 구현하고, 팀원은 §9의 케이스 표를 `pytest.mark.parametrize`로 옮긴다.

## 1. 확정 결정 요약

| 항목 | 결정 |
|---|---|
| 상태 코드 | `OK`, `CAUTION`, `BLOCKED`, `NEEDS_CHECK` (가능 / 주의 / 불가 / 확인 필요). PRD 표기(GREEN·AMBER·RED·UNKNOWN) 대신 이 이름을 API에 쓴다 |
| ① 병해충 미지목 | **`NEEDS_CHECK`.** 병해충을 모르면 이 병해충에 등록됐는지 확인할 수 없다. 작물 자체에 등록이 없으면 그대로 `BLOCKED` |
| ② 시기 | 수확 예정일을 입력받지 않는다. **"오늘 살포하면 N월 N일부터 수확 가능"을 계산해 표시**한다. ②는 `BLOCKED`를 내지 않는다 |
| ② 사용 방법별 규칙 | 같은 병해충에 사용 방법이 여럿이면 **가장 엄격한 값**(수확 전 일수 최대, 횟수 최소)을 쓰고, 사용 방법이 둘 이상이면 어느 사용 방법 기준인지 문구에 밝힌다. 사용 방법을 사용자가 고르는 기능은 P1 (§10-8). 판정은 수확 전 사용 기준(PHI)만 본다 (§10-7) |
| 사용 유형 `usage_type` | 엑셀 변환 구분: `NORMAL`(성공), `AT_PLANTING`(심을 때), `NO_LIMIT`(제한 없음), `CHECK`(확인 필요). `NO_LIMIT`은 ②③ `OK`(라벨 안내), `AT_PLANTING`은 ② `NEEDS_CHECK`(심을 때 쓰는 약), `CHECK`는 NULL로 본다 (§3) |
| ③ 집계 단위 | **품목명(`item_name`) 기준 합산.** 같은 품목의 다른 상표 이력도 같은 약으로 센다. 성분 단위 합산은 미확인 (§10-1) |
| ③ 횟수 창 | 정식일(`planted_at`) 이후 (KST). **정식일이 없으면 `NEEDS_CHECK`.** 지원 작물(감자·배추·토마토)이 모두 일년생이라 다년생 창은 두지 않는다. "N회 이내" = 최대 N회까지 허용 |
| ③ 표시 | **현재 남은 횟수 / 이번 사용 후 남을 횟수.** 마지막 1회는 `OK`이고 문구로만 알린다. `CAUTION` 없음 |
| 이력 확인 | 구역의 「누락 없음」 확인(`history_confirmed`)이 없으면 **이력 건수와 무관하게** ③④ = `NEEDS_CHECK`. 확인했고 이력이 0건이면 ③④를 계산한다(`OK`). 정식일이 바뀌면 확인이 풀린다 (서비스 규칙) |
| ④ 반복 규칙 | 계열별 **연속 허용 횟수**(`6_반복규칙`). 직전까지 같은 작용기작이 연속으로 허용 횟수 이상이면 `CAUTION`. 제한 없는 계열이 있다 (§4 ④) |
| ④ 성격 | 효과 문제. `BLOCKED` 없음 |
| `moa` NULL | 고른 약제의 `moa`가 NULL이면 ④ = `NEEDS_CHECK` (엑셀에서 계열 코드가 없는 17줄이 해당) |
| 병해충 미지목 ②③ | 고려 대상 행 전체의 가장 엄격한 값 (PHI 최대, 횟수 최소) + 안내 문구. 대안은 계산하지 않음 |
| 근거 | **체크 4개 모두 `evidence`가 항상 있다.** 원문이 비면 「없음」. `data_asof`도 항상 있다 |
| 편중도(`rotation`) | 작기 전체 비율. 정식일이 없으면 전체 이력. ④ 판정과 별개 함수 |
| 대안 | 같은 작물×병해충의 다른 약제 중 `OK`이고 작용기작이 다른 것. 상세는 §7 |
| 문구 | 백엔드가 생성한다. 예측·추천·확률·"안전" 표현 금지 (§8) |

## 2. 타입

`judgment/domain/schemas.py` (Pydantic). 이 모듈과 `judgment/domain/rules.py`는 DB·HTTP를 임포트하지 않는다.

```python
class Verdict(str, Enum):        # 가능 / 주의 / 불가 / 확인 필요
    OK, CAUTION, BLOCKED, NEEDS_CHECK
PRIORITY = {BLOCKED: 3, NEEDS_CHECK: 2, CAUTION: 1, OK: 0}

class Moa:           label_kr, system: str | None, code: str | None
                     # label_kr = 국내 계열 코드 (예: "라3", 복합제는 "카+가1"). system/code = 국제 코드 (엑셀 5_약계열의 「FRAC 24」를 나눈 값)

class Registration:                  # 고른 상표(pesticide_id)의 이 작물에 대한 엑셀 행 (사용 방법별)
    pest_id: int
    pest_name: str
    phi_days: int | None             # use_suittime_raw 파싱 결과
    max_uses: int | None             # use_num_raw 파싱 결과
    use_suittime_raw: str | None     # 예: "수확14일전" (엑셀 사용 시기 원문)
    use_num_raw: str | None          # 예: "5회" (엑셀 사용 횟수 원문)
    dilut_raw: str | None            # 희석배수 원문
    use_method: str | None           # 사용 방법 (예: "발생 초부터 경엽처리", "정식 전 토양처리")
    usage_type: str                  # NORMAL | AT_PLANTING | NO_LIMIT | CHECK (엑셀 변환 구분)
    data_asof: date                  # 엑셀 기준일 (2026-10-05)

class SprayRecord:
    id: int
    pesticide_id: int
    item_name: str
    sprayed_on: date
    moa: Moa | None

class JudgeInput:
    today: date                      # 주입. 시계 없이 테스트한다. KST 기준. API의 apply_date가 있으면 그 날짜
    planted_at: date | None          # None = 정식일 미입력
    history_confirmed: bool          # 「누락 없음」 확인 여부
    pest_id: int | None              # None = 병해충 미지목
    pesticide_id: int
    item_name: str
    moa: Moa | None
    registrations: list[Registration]   # 고른 상표의 이 작물 행 전부 (병해충 무관). 서비스가 psis_use_seq 순으로 넘긴다
    history: list[SprayRecord]          # 구역 전체 이력
    psis_asof: date                     # 엑셀 기준일 (이름은 옛 PSIS 적재일에서 왔다). 고려 행이 없을 때 data_asof로 쓴다

class Evidence:      source_text: str, data_asof: date
class CheckResult:   key, status: Verdict, message: str, facts: dict, evidence: Evidence
                     # key = registration | timing | count | moa. evidence는 항상 있다

class JudgeResult:
    pesticide_id: int
    moa: Moa | None
    verdict: Verdict                 # checks 중 PRIORITY 최고값
    checks: list[CheckResult]        # 항상 4개, 순서 registration, timing, count, moa
    notices: list[str]
    data_asof: date                  # 고려한 행들의 data_asof 중 가장 오래된 값, 행이 없으면 psis_asof. 화면 표기는 "데이터 조회일"

class RotationRule:    kind: str, max_consecutive: int | None, source: str
                       # kind = NO_LIMIT | CONSECUTIVE. source = 규칙 출처 (6_반복규칙)
class RotationItem:    moa: Moa | None, count: int       # None = 작용기작 미상
class RotationSummary: window_start: date | None, total: int, items: list[RotationItem]
                       # window_start None = 정식일 없음, 전체 이력 기준

def judge(inp: JudgeInput) -> JudgeResult
def rotation_summary(history, planted_at) -> RotationSummary
def rotation_rule(moa: Moa) -> RotationRule                   # 4절 ④의 규칙 표
def pick_alternatives(selected: JudgeResult, others: list[JudgeResult]) -> list[JudgeResult]
```

`Alternative`(`id, name, item_name, moa`)은 서비스가 `pick_alternatives` 결과에 이름을 채워 만든다. API에서는 `Pesticide`와 같은 모양이라 약제 id 필드 이름이 `id`다 (`JudgeResult.pesticide_id`는 판정 안의 이름이라 그대로).

## 3. 공통 규칙

**고려 대상 행(`rows`).**
- `pest_id`가 있으면 `registrations` 중 `pest_id`가 같은 행.
- `pest_id`가 None이면 `registrations` 전부.
- **계산용 행(`calc_rows`).** `rows`에서 먼저 `AT_PLANTING` 행을, 그다음 `NO_LIMIT` 행을 뺀다. 단, **빼고 나서 행이 남을 때만** 뺀다 (전부 같은 유형이면 그대로 둔다).
  - `calc_rows`가 전부 `AT_PLANTING`이면 ②는 `NEEDS_CHECK`(심을 때 쓰는 약), ③은 `max_uses`로 계산한다.
  - `calc_rows`가 전부 `NO_LIMIT`이면 ②③은 `OK`(제한 없음)이다. 값이 비어 있는 것이 정상이다.
- 같은 대상에 행이 여럿이면 ②는 `phi_days` 최댓값, ③은 `max_uses` 최솟값 (가장 엄격한 값). 기준이 된 행의 `use_method`를 `facts.strict_use_method`에 넣고, `calc_rows`의 `use_method`가 둘 이상이면 문구에 「{use_method} 기준」을 붙인다.
- **`CHECK` 행과 값이 NULL인 `NORMAL` 행은 NULL로 본다. `calc_rows`에 NULL이 하나라도 있으면 그 체크는 `NEEDS_CHECK`.** 읽지 못한 행이 더 엄격할 수 있기 때문이다 (보수적 선택). 원문은 NULL인 행의 것을 보여준다.

**횟수 창.** `planted_at` 이후. `planted_at`이 None이면 창이 없다 (③ `NEEDS_CHECK`). 다년생 분기는 두지 않는다. 다년생 작물을 지원하게 되면 「올해 1/1」 창을 되살린다.

**날짜 표기(`message`).** `today`와 같은 해면 「10월 11일」, 다른 해면 「2027년 1월 8일」. `facts`와 `Evidence`의 날짜는 ISO 문자열.

**근거(`evidence`).** 체크 4개 모두 있다. `source_text`로 쓸 원문이 NULL이거나 빈 문자열이면 「없음」. `evidence.data_asof` = `JudgeResult.data_asof`.

## 4. 체크별 규칙

판정 순서는 위에서 아래로 첫 번째로 맞는 줄에서 멈춘다.

### ① registration (등록)

| 조건 | status | facts |
|---|---|---|
| `registrations`가 비어 있음 | `BLOCKED` (작물 미등록) | `{crop_registered: false}` |
| `pest_id` 있음, `rows`가 비어 있음 | `BLOCKED` (다른 병해충에만 등록) | `{crop_registered: true, registered_pests: [이름…]}` |
| `pest_id`가 None | `NEEDS_CHECK` (병해충 미지정) | `{crop_registered: true, pest_specified: false, registered_pests: [이름…]}` |
| 그 외 | `OK` | `{pest_specified: true, rows: n}` |

`evidence.source_text`:
- `OK`: `rows` 첫 행의 `use_method`와 `dilut_raw` 중 값이 있는 것을 " · "로 연결 (예: 「발생 초부터 경엽처리 · 1000배」). 둘 다 없으면 「없음」.
- `registered_pests`가 있는 두 경우: 「등록 병해충: 역병, 탄저병」 (이름순).
- 작물 미등록: 「없음」.

### ② timing (시기)

| 조건 | status |
|---|---|
| ①이 `BLOCKED` | `NEEDS_CHECK` (등록 정보 없음) |
| `calc_rows`가 전부 `AT_PLANTING` | `NEEDS_CHECK` (심을 때 쓰는 약) |
| `calc_rows` 중 `phi_days` NULL이 있음 (`CHECK` 포함) | `NEEDS_CHECK` (원문 표시) |
| `calc_rows`가 전부 `NO_LIMIT` | `OK` (제한 없음, 라벨 안내) |
| `phi = max(phi_days)` = 0 | `OK` (수확 당일까지) |
| `phi` ≥ 1 | `OK` |

- ①이 `NEEDS_CHECK`(병해충 미지정)인 경우는 ②를 막지 않는다. `rows` 전부로 `calc_rows`를 만들어 가장 엄격한 값으로 계산한다.
- `NO_LIMIT` 행이 `NORMAL` 행과 섞여 있으면 `NO_LIMIT` 행은 계산에서 빠진다 (`phi`는 `NORMAL` 행에서).
- `facts = {phi_days, harvest_from, rows, strict_use_method, no_limit}`, `harvest_from = today + phi` (`NO_LIMIT`이면 `phi_days`·`harvest_from` = None, `no_limit = true`). `evidence.source_text` = 가장 엄격한 행(NEEDS_CHECK면 NULL인 행)의 `use_suittime_raw`, ①이 `BLOCKED`면 「없음」. **`BLOCKED`는 내지 않는다.**

### ③ count (횟수)

| 조건 | status |
|---|---|
| ①이 `BLOCKED` | `NEEDS_CHECK` (등록 정보 없음) |
| `calc_rows` 중 `max_uses` NULL이 있음 (`CHECK` 포함) | `NEEDS_CHECK` (원문 표시) |
| `calc_rows`가 전부 `NO_LIMIT` | `OK` (제한 없음. 정식일·누락 확인과 무관) |
| `planted_at`이 None | `NEEDS_CHECK` (정식일 없음) |
| `history_confirmed`가 false | `NEEDS_CHECK` (누락 확인 전. 이력 건수 무관) |
| `used >= max` | `BLOCKED` |
| 그 외 | `OK` |

- `max = min(max_uses)` (`calc_rows` 중 `NORMAL`·`AT_PLANTING` 행). `NO_LIMIT` 행이 섞여 있으면 빠진다.
- `used` = `history` 중 `item_name`이 같고 `sprayed_on >= planted_at`인 건수. 같은 날 여러 건은 각각 1건. 이력이 있지만 창 안에 없으면 `used = 0` (확인 필요가 아님).
- 이번 살포는 `used + 1`번째. `remaining = max - used`, `remaining_after = remaining - 1`. `remaining == 1`이면 마지막 횟수 문구를 쓴다 (상태는 `OK`).
- `BLOCKED`이면 `remaining = 0`(초과 사용이어도 0), `remaining_after = None`.
- `facts = {used, max_uses, remaining, remaining_after, since, item_name, strict_use_method, no_limit}`. `evidence.source_text` = 가장 엄격한 행(NEEDS_CHECK면 NULL인 행)의 `use_num_raw`, ①이 `BLOCKED`면 「없음」.
- 앞쪽 조건이 먼저 걸리는 이유: 사용자가 고칠 수 없는 원인(등록·기준 읽기 실패)을 먼저 보여주고, 그다음 사용자가 채울 정보(정식일 → 누락 확인)를 보여준다.

### ④ moa (작용기작)

| 조건 | status |
|---|---|
| 고른 약제 `moa`가 None | `NEEDS_CHECK` |
| `history_confirmed`가 false | `NEEDS_CHECK` (누락 확인 전. 이력 건수 무관) |
| 규칙이 `NO_LIMIT` | `OK` (제한 없는 계열) |
| `history`가 비어 있음 | `OK` (연속 0회) |
| `consecutive >= max_consecutive` | `CAUTION` |
| 그 외 | `OK` |

**규칙 표 (`rotation_rule(moa)`).** 출처는 엑셀 `6_반복규칙`이다. 위에서 아래로 첫 번째로 맞는 줄을 쓴다.

| 대상 | 규칙 | 출처 |
|---|---|---|
| FRAC M (`카`), IRAC 8 (`8a`~`8f`), IRAC 13 (`13`), 미분류(IRAC UN, `미분류`) | `NO_LIMIT` | FRAC Multi-site Guidelines, IRAC 예외 그룹 |
| FRAC 4 (`가1`), FRAC 40 (`아5`) | `CONSECUTIVE`, 연속 2회까지 | FRAC Phenylamides, FRAC CAA WG |
| 그 밖의 IRAC (`system = IRAC`, 살충제) | `CONSECUTIVE`, 연속 2회까지 | IRAC MoA Classification v11.5 |
| 그 밖의 계열 (살균제 등) | `CONSECUTIVE`, 연속 1회까지 | 농식품부 PLS 안내 |

- **복합 계열**(`label_kr`에 `+`, 예 `카+가1`)은 성분별로 위 표를 적용해 **가장 엄격한 것**을 쓴다 (`NO_LIMIT`은 무한으로 본다). 성분의 `system`을 알 수 없으면 「그 밖의 계열」로 본다.
- `6_반복규칙`의 「시즌 최대」(2~4회, 계획 살포의 50%)와 「같은 세대(약 30일) 안」 조건은 판정에 쓰지 않고, 규칙 출처 문구에만 남긴다 (§10-9).
- `consecutive` = `history`를 `sprayed_on` 내림차순, 같은 날이면 `id` 내림차순으로 정렬해 **앞에서부터** 고른 약제와 `moa.label_kr`이 같은 기록이 이어지는 건수. 다른 계열이나 `moa`가 None인 기록을 만나면 끊긴다. **이번 살포는 `consecutive + 1`번째**이므로 `consecutive >= max_consecutive`이면 허용 횟수를 넘는다. 작기와 무관하다 (`planted_at`이 None이어도 계산).
- `window` = 위 정렬의 **앞 3건** (표시용, 3건 미만이면 있는 만큼). `unknown` = `window` 중 `moa`가 None인 건수.
- ④는 ①의 결과와 무관하게 계산한다.
- `facts = {label, rule: "NO_LIMIT"|"CONSECUTIVE", max_consecutive, consecutive, unknown, window}`. `window` = `[{id, sprayed_on, item_name, label | None}]` (최근순). 화면이 비교 근거로 보여준다.
- `evidence.source_text` = 적용한 규칙의 출처 (예 「FRAC Phenylamides (last updated March 2020)」), `moa`가 None이면 「없음」.

## 5. 최종 판정과 notices

- `verdict` = 4개 체크 `status` 중 `PRIORITY`가 가장 높은 값.
- `notices`: `pest_id`가 None이고 `registrations`가 비어 있지 않으면 「병해충을 지정하지 않아 가장 엄격한 기준을 적용했습니다」 한 줄.
- `data_asof` = 고려한 `rows`의 `data_asof` 중 최솟값. `rows`가 없으면 `psis_asof`.
- 서비스가 `pest_id`가 None이고 `verdict`가 `BLOCKED`이면 `notices`에 「병해충을 지정하면 대안을 볼 수 있습니다」를 추가한다. (미지정이면 ①이 `NEEDS_CHECK`라 `verdict`는 `BLOCKED` 또는 `NEEDS_CHECK`뿐이다.)

## 6. 편중도 (`rotation_summary`)

- 창 = `planted_at` 이후 `history` 전체. `planted_at`이 None이면 `history` 전체이고 `window_start = None`. 약제 수와 무관하게 **살포 건수**로 센다.
- 작용기작별(`moa.label_kr`)로 묶어 `count`를 센다. `moa`가 None인 건은 `moa: None` 항목 하나로 센다.
- 정렬: `count` 내림차순, 같으면 `label_kr` 오름차순, `None` 항목은 맨 뒤.
- `total` = 창 안의 전체 건수. 이력이 없으면 `total = 0`, `items = []`. 비율은 프론트가 `count / total`로 계산한다.
- `history_confirmed`와 무관하다 (있는 기록을 보여주는 화면이다).
- ④ 판정(연속 횟수 규칙)과 별개다. 두 함수가 서로의 결과를 쓰지 않는다.

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
- `show_extension_office = true` 조건: 병해충을 지목했고, `verdict`가 `BLOCKED` 또는 `CAUTION`이며, 대안이 0건일 때만. (병해충 미지목이면 병해충을 지정했을 때 대안이 있을 수 있으므로 문의 안내를 띄우지 않는다.)

## 8. 문구

**작성 규칙:** 존댓말, 사실만 서술한다. 예측·추천·확률·"안전하다"는 뜻의 표현은 쓰지 않는다. **금지어 테스트 대상: `추천 예측 예상 가능성 위험 확률 안전 문제없`.** ("수확 가능"은 계산 결과라 허용, "가능성"만 금지.) 금지어 검사는 판정 문구(`message`·`notices`)에만 적용한다. 기상청 용어 「강수확률」 같은 외부 데이터 표기는 대상이 아니다.

| 체크 | 상태 | 조건 | message |
|---|---|---|---|
| ① 등록 | OK | 병해충 지목 | 이 병해충에 등록된 약제입니다 |
| | NEEDS_CHECK | 병해충 미지목 | 병해충을 지정하지 않아 등록 여부를 확인할 수 없습니다 (이 작물에는 등록되어 있습니다) |
| | BLOCKED | 다른 병해충에만 등록 | 이 병해충에는 등록되어 있지 않습니다 (이 작물에 등록된 병해충 {n}종) |
| | BLOCKED | 작물에 등록 없음 | 이 작물에는 등록되어 있지 않습니다 |
| ② 시기 | OK | `phi_days` ≥ 1 | 오늘 살포하면 {harvest_from}부터 수확할 수 있습니다 (수확 {phi}일 전까지 사용) |
| | OK | `phi_days` = 0 | 수확 당일까지 사용할 수 있습니다 |
| | OK | `NO_LIMIT` | 수확 전 사용 일수 제한이 없는 약제입니다. 라벨의 사용 방법을 확인해 주세요 |
| | NEEDS_CHECK | 전부 `AT_PLANTING` | 이 약은 심을 때(정식기·파종기) 쓰는 약입니다. 수확 전 사용 기준이 없어 수확 가능일을 계산할 수 없습니다. 원문: {raw} |
| | NEEDS_CHECK | `phi_days` NULL | 수확 전 사용 기준을 읽지 못했습니다. 원문: {raw} |
| | NEEDS_CHECK | ①이 BLOCKED | 등록 정보가 없어 확인할 수 없습니다 |
| ③ 횟수 | OK | `remaining` ≥ 2 | 남은 횟수 {remaining}회, 이번 사용 후 {remaining_after}회입니다 (최대 {max}회) |
| | OK | `remaining` = 1 | 남은 횟수 1회, 이번 사용 후 0회입니다 (최대 {max}회). 이번이 마지막 사용입니다 |
| | OK | `NO_LIMIT` | 사용 횟수 제한이 없는 약제입니다. 라벨의 사용 방법을 확인해 주세요 |
| | BLOCKED | `used >= max` | {since}부터 {used}회 사용해 최대 {max}회를 채웠습니다. 남은 횟수는 0회입니다 |
| | NEEDS_CHECK | 정식일 없음 | 정식일이 없어 이번 작기 사용 횟수를 셀 수 없습니다. 정식일을 입력해 주세요 |
| | NEEDS_CHECK | 누락 확인 전 | 살포 기록에 빠진 것이 없는지 확인되지 않았습니다. 기록을 입력하고 「누락 없음」을 선택해 주세요 |
| | NEEDS_CHECK | `max_uses` NULL | 최대 사용 횟수 기준을 읽지 못했습니다. 원문: {raw} |
| | NEEDS_CHECK | ①이 BLOCKED | 등록 정보가 없어 확인할 수 없습니다 |
| ④ 작용기작 | OK | 규칙 `NO_LIMIT` | {label} — 같은 계열을 반복해도 제한이 없는 계열입니다 |
| | OK | 누락 없음 + 이력 0건 | 살포 이력이 없습니다 |
| | OK | 연속 0회 | {label} — 직전 살포는 다른 계열입니다 |
| | OK | 0 < 연속 < 허용 | {label} — 직전까지 같은 계열을 연속 {consecutive}회 사용했습니다 (연속 {max_consecutive}회까지 기준) |
| | CAUTION | 연속 ≥ 허용 | {label} — 직전까지 같은 계열을 연속 {consecutive}회 사용했습니다. 연속 {max_consecutive}회까지가 기준이라 같은 작용기작이 반복됩니다 |
| | NEEDS_CHECK | 누락 확인 전 | 살포 기록에 빠진 것이 없는지 확인되지 않았습니다. 기록을 입력하고 「누락 없음」을 선택해 주세요 |
| | NEEDS_CHECK | 고른 약제 `moa` NULL | 이 약제의 작용기작 정보가 없어 비교할 수 없습니다 |

- `{n}` = `registered_pests`의 개수.
- `{label}`은 `moa.label_kr`, `system`과 `code`가 있으면 「가1 (FRAC 4)」.
- ④에서 `unknown ≥ 1`이면 `message` 끝에 「 (작용기작 미상 {unknown}건 포함)」을 붙인다.
- ②③에서 `calc_rows`의 `use_method`가 둘 이상이면 `OK`·`BLOCKED` 문구 끝에 「 ({use_method} 기준)」을 붙인다 (예: 「…(수확 21일 전까지 사용) (무인항공 기준)」).
- `{raw}`는 NULL인 행의 원문. 원문 자체가 비어 있으면 「없음」.

**범위 밖(프론트 고정 문구):** 「횟수는 정식일 이후 기준으로 집계합니다」, "가능"이 사용 보증으로 읽히지 않게 하는 **면책 한 줄**(제품·법무와 정함, §10-4), 매개충 안내 「이 바이러스를 옮기는 해충입니다. 아래 약제는 이 해충에 등록된 약제이며 바이러스를 치료하지 않습니다」.

## 9. 테스트 케이스 표

기준 픽스처 `base`: `today = 2026-10-04`, `planted_at = 2026-05-01`, `history_confirmed = true`, `pest_id = 1`(탄저병), 고른 약제 = 상표 10 / 품목 「품목A」 / `moa` 「가1」(FRAC 4), `registrations = [pest 1, phi 7, max 3, use_suittime_raw "수확 7일 전까지", use_num_raw "3회 이내", dilut "1000배", use_method "발생 초부터 경엽처리", usage_type NORMAL, data_asof 2026-10-01]`, `history = []`, `psis_asof = 2026-10-03`.

이력 표기: `품목A(가1)@2026-06-01` = 품목A, 작용기작 가1, 살포일. 기재 없는 항목은 `base` 그대로. **판정에 영향이 없는 체크는 비교하지 않는다.**

### 등록 ①
| ID | 입력 변경 | 기대 |
|---|---|---|
| R1 | (`base`) | ① `OK`, 「이 병해충에 등록된 약제입니다」, evidence 「발생 초부터 경엽처리 · 1000배」 |
| R2 | `registrations = [pest 2 "역병" 1행]` | ① `BLOCKED`, 「이 병해충에는 등록되어 있지 않습니다 (이 작물에 등록된 병해충 1종)」, `facts.registered_pests = ["역병"]`, evidence 「등록 병해충: 역병」. ②③ `NEEDS_CHECK` 「등록 정보가 없어 확인할 수 없습니다」, evidence 「없음」. `verdict = BLOCKED` |
| R3 | `registrations = []` | ① `BLOCKED`, 「이 작물에는 등록되어 있지 않습니다」, evidence 「없음」, `data_asof = 2026-10-03` (`psis_asof`) |
| R4 | `pest_id = None` | ① `NEEDS_CHECK`, 「병해충을 지정하지 않아 등록 여부를 확인할 수 없습니다 (이 작물에는 등록되어 있습니다)」, `facts.registered_pests = ["탄저병"]`, `notices = ["병해충을 지정하지 않아 가장 엄격한 기준을 적용했습니다"]`, `verdict = NEEDS_CHECK` |
| R5 | `pest_id = None`, `registrations = []` | ① `BLOCKED`, `notices = []` |

### 시기 ②
| ID | 입력 변경 | 기대 |
|---|---|---|
| T1 | (`base`) | ② `OK`, `harvest_from = 2026-10-11`, 「오늘 살포하면 10월 11일부터 수확할 수 있습니다 (수확 7일 전까지 사용)」, evidence 「수확 7일 전까지」 |
| T2 | `phi_days = 0` | ② `OK`, 「수확 당일까지 사용할 수 있습니다」, `harvest_from = 2026-10-04` |
| T3 | `phi_days = None`, `use_suittime_raw = "수확 직전"` | ② `NEEDS_CHECK`, 「수확 전 사용 기준을 읽지 못했습니다. 원문: 수확 직전」 |
| T4 | `pest_id = None`, 행 = pest 1(phi 7), pest 2(phi 14) | ② `OK` (① `NEEDS_CHECK`여도 계산), `phi_days = 14`, `harvest_from = 2026-10-18` |
| T5 | 행 = pest 1(phi 7), pest 1(phi 10), pest 2(phi 30) | `phi_days = 10` (pest 2 행은 무시) |
| T6 | 행 = pest 1(phi 7), pest 1(phi None) | ② `NEEDS_CHECK` |
| T7 | `today = 2026-12-25`, `phi_days = 14` | 「오늘 살포하면 2027년 1월 8일부터 수확할 수 있습니다 (수확 14일 전까지 사용)」 |
| T8 | 행 전부 `NO_LIMIT` (phi None, `use_suittime_raw = "발생초기"`) | ② `OK`, 「수확 전 사용 일수 제한이 없는 약제입니다. 라벨의 사용 방법을 확인해 주세요」, `phi_days = None`, `no_limit = true`, evidence 「발생초기」 |
| T9 | 행 전부 `AT_PLANTING` (phi None, `use_suittime_raw = "정식기"`) | ② `NEEDS_CHECK`, 「이 약은 심을 때(정식기·파종기) 쓰는 약입니다. … 원문: 정식기」 |
| T10 | 행 = `AT_PLANTING`(phi None) + `NORMAL`(phi 7) | ② `OK`, `phi_days = 7` (심을 때 행은 계산에서 뺀다) |
| T11 | 행 = `NORMAL`(phi 7) + `NO_LIMIT` | ② `OK`, `phi_days = 7` |
| T12 | 행 = `CHECK` (phi None, `use_suittime_raw = "수확7일"`) | ② `NEEDS_CHECK`, 「수확 전 사용 기준을 읽지 못했습니다. 원문: 수확7일」 |
| T13 | 행 = `NORMAL` 경엽처리(phi 14), `NORMAL` 무인항공(phi 21) | ② `OK`, `phi_days = 21`, `strict_use_method = "무인항공"`, 문구 끝에 「 (무인항공 기준)」 |
| T14 | 행 = `AT_PLANTING`(phi None) + `NO_LIMIT` | `AT_PLANTING` 행을 먼저 빼고 `NO_LIMIT`만 남아 ② `OK` (제한 없음) |

### 횟수 ③
| ID | 입력 변경 | 기대 |
|---|---|---|
| C1 | `history = [품목B(나2)@06-01]` | `used = 0`, `OK`, 「남은 횟수 3회, 이번 사용 후 2회입니다 (최대 3회)」 |
| C2 | `history = [품목A(가1)@06-01]` | `used = 1`, `remaining = 2`, `remaining_after = 1`, 「남은 횟수 2회, 이번 사용 후 1회입니다 (최대 3회)」 |
| C3 | `history = [품목A@06-01, 품목A@06-15]` | `used = 2`, 「남은 횟수 1회, 이번 사용 후 0회입니다 (최대 3회). 이번이 마지막 사용입니다」, 상태 `OK` |
| C4 | `history = [품목A@06-01, 06-15, 07-01]` | `used = 3`, `BLOCKED`, 「5월 1일부터 3회 사용해 최대 3회를 채웠습니다. 남은 횟수는 0회입니다」, `remaining = 0`, `remaining_after = None` |
| C5 | `history = [품목A@2026-04-20, 품목A@2026-06-01]` | `used = 1` (정식일 이전 이력 제외) |
| C6 | `planted_at = None`, `history = [품목A(가1)@06-01]` | ③ `NEEDS_CHECK`, 「정식일이 없어 이번 작기 사용 횟수를 셀 수 없습니다. 정식일을 입력해 주세요」. ④는 계산 (`OK`, 「가1 (FRAC 4) — 직전까지 같은 계열을 연속 1회 사용했습니다 (연속 2회까지 기준)」) |
| C7 | `history = [품목A(상표 10)@06-01, 품목A(상표 11)@06-10]` | `used = 2` (같은 품목은 상표가 달라도 합산) |
| C8 | `history = [품목B@06-01]` | `used = 0` |
| C9 | `history = []`, `history_confirmed = false` | ③ `NEEDS_CHECK`, 「살포 기록에 빠진 것이 없는지 확인되지 않았습니다. …」 |
| C10 | `history = []` (`history_confirmed = true`) | `used = 0`, `OK`, 「남은 횟수 3회, 이번 사용 후 2회입니다 (최대 3회)」 |
| C11 | `max_uses = None`, `use_num_raw = "-"` | ③ `NEEDS_CHECK`, 「최대 사용 횟수 기준을 읽지 못했습니다. 원문: -」 |
| C12 | `history = [품목A@06-01, 품목A@06-01]` | `used = 2` (같은 날 2건은 각각 1회) |
| C13 | `pest_id = None`, 행 = pest 1(max 5), pest 2(max 3) | `max = 3` |
| C14 | `history = [품목A@2026-04-01]` | `used = 0`, `OK` (이력은 있으나 창 밖이라 확인 필요가 아님) |
| C15 | `history = [품목A@06-01]`, `history_confirmed = false` | ③ `NEEDS_CHECK` (누락 확인 전. 이력이 있어도) |
| C16 | `planted_at = None`, `history_confirmed = false` | ③ 「정식일이 없어 …」 (정식일 줄이 먼저) |
| C17 | `history = [품목A@06-01, 06-15, 07-01, 08-01]` | `used = 4`, `BLOCKED`, `remaining = 0` (초과 사용도 0) |
| C18 | 행 전부 `NO_LIMIT`, `planted_at = None`, `history_confirmed = false` | ③ `OK`, 「사용 횟수 제한이 없는 약제입니다. 라벨의 사용 방법을 확인해 주세요」 (정식일·누락 확인과 무관) |
| C19 | 행 전부 `AT_PLANTING` (max 1), `history = []` | ③ `OK`, `used = 0`, 「남은 횟수 1회, … 이번이 마지막 사용입니다」 (② 는 `NEEDS_CHECK`) |
| C20 | 행 = `NORMAL` 경엽처리(max 3), `NORMAL` 무인항공(max 1) | `max = 1`, `strict_use_method = "무인항공"`, 문구에 「 (무인항공 기준)」 |
| C21 | 행 = `NORMAL`(max 3) + `NO_LIMIT` | `max = 3` (`NO_LIMIT` 행은 뺀다) |

### 작용기작 ④ (고른 약제 `moa` = 가1 (FRAC 4), 연속 2회까지)
이력은 **최근순**으로 적는다. 계열 이름만 적으면 작용기작이고, `미상`은 `moa = None`이다.

| ID | 입력 변경 | 기대 |
|---|---|---|
| M1 | `history = []` (`history_confirmed = true`) | ④ `OK`, 「살포 이력이 없습니다」, `consecutive = 0`, `window = []` |
| M2 | `history = []`, `history_confirmed = false` | ④ `NEEDS_CHECK`, 「살포 기록에 빠진 것이 없는지 확인되지 않았습니다. …」 |
| M3 | `[가1, 나2, 가1]` | `consecutive = 1`, `OK`, 「가1 (FRAC 4) — 직전까지 같은 계열을 연속 1회 사용했습니다 (연속 2회까지 기준)」, evidence 「FRAC Phenylamides (last updated March 2020)」 |
| M4 | `[가1, 가1, 나2]` | `consecutive = 2`, `CAUTION`, 「가1 (FRAC 4) — 직전까지 같은 계열을 연속 2회 사용했습니다. 연속 2회까지가 기준이라 같은 작용기작이 반복됩니다」, `window`는 3건 (최근순) |
| M5 | `[나2, 가1, 가1]` | `consecutive = 0`, `OK`, 「가1 (FRAC 4) — 직전 살포는 다른 계열입니다」 (오래된 가1 두 건은 연속이 아니다) |
| M6 | 고른 약제 `moa = None` (이력은 무관) | ④ `NEEDS_CHECK`, 「이 약제의 작용기작 정보가 없어 비교할 수 없습니다」, evidence 「없음」 |
| M7 | `[미상, 가1, 가1]` | `consecutive = 0` (미상이 연속을 끊는다), `OK`, 「가1 (FRAC 4) — 직전 살포는 다른 계열입니다 (작용기작 미상 1건 포함)」, `unknown = 1` |
| M8 | 같은 날(09-01) `id 4(가1)`, `id 5(나2)` + 08-30 `id 3(가1)` | 정렬 = id 5, 4, 3. `consecutive = 0` (맨 앞이 나2), `OK` |
| M9 | `[가1, 가1]`, `history_confirmed = false` | ④ `NEEDS_CHECK` (`CAUTION`이 아님) |
| M10 | 고른 약제 `moa = 카 (FRAC M)`, `[카, 카, 카]` | 규칙 `NO_LIMIT`, `OK`, 「카 (FRAC M) — 같은 계열을 반복해도 제한이 없는 계열입니다」 |
| M11 | 고른 약제 `moa = 8f (IRAC 8F)`, `[8f, 8f, 8f]` | `NO_LIMIT`, `OK` (IRAC 8 예외) |
| M12 | 고른 약제 `moa = 28 (IRAC 28)`, `[28, 28, 나2]` | 그 밖의 IRAC, `max_consecutive = 2`, `consecutive = 2`, `CAUTION` |
| M13 | 고른 약제 `moa = 28 (IRAC 28)`, `[28, 나2]` | `consecutive = 1`, `OK` |
| M14 | 고른 약제 `moa = 다3 (FRAC 3)` (표에 없는 살균제), `[다3]` | `max_consecutive = 1`, `consecutive = 1`, `CAUTION` |
| M15 | 고른 약제 `moa = 카+가1`, `[카+가1, 카+가1]` | 복합 계열 = `카`(`NO_LIMIT`)와 `가1`(2회) 중 엄격한 쪽, `max_consecutive = 2`, `consecutive = 2`, `CAUTION` |
| M16 | 고른 약제 `moa = 카+라3`, `[카+라3]` | `라3`은 「그 밖의 계열」(1회), `max_consecutive = 1`, `CAUTION` |
| M17 | 고른 약제 `moa = 가1 (FRAC 4)`, `[가1, 가1, 가1]` | `consecutive = 3`, `CAUTION` (허용 횟수를 이미 넘었어도 같은 상태) |

### 최종 판정 · 기타
| ID | 입력 | 기대 |
|---|---|---|
| V1 | ① `BLOCKED` + ④ `CAUTION` | `verdict = BLOCKED` |
| V2 | ③ `NEEDS_CHECK` + ④ `CAUTION` | `verdict = NEEDS_CHECK` |
| V3 | ④ `CAUTION`, 나머지 `OK` | `verdict = CAUTION` |
| V4 | 모두 `OK` | `verdict = OK`, `checks`는 4개, 순서 registration, timing, count, moa |
| V5 | 행 `data_asof`가 2026-10-01, 2026-09-20 | `data_asof = 2026-09-20` |
| V6 | `base`, R2, R3, M6 | 4개 체크 모두 `evidence`가 있고 `evidence.data_asof = data_asof` |
| V7 | `pest_id = None`, 나머지 `base` | `verdict = NEEDS_CHECK` (①만 확인 필요) |
| RT1 | `planted_at = 2026-05-01`, 이력: 가1 4건(정식일 이후) + 가1 1건(정식일 이전) + 나2 2건 + 미상 1건 | `window_start = 2026-05-01`, `total = 7`, `items = [가1:4, 나2:2, None:1]` |
| RT2 | `history = []` | `total = 0`, `items = []` |
| RT3 | `planted_at = None`, 이력: 가1@2025-08-01, 가1@2026-06-01, 나2@2026-07-01 | `window_start = None`, `total = 3`, `items = [가1:2, 나2:1]` |
| A1 | 다른 약제 `OK`, `moa` 나2 | 대안에 포함 |
| A2 | 다른 약제 `OK`, `moa` 가1 (같은 품목 다른 상표) | 제외 |
| A3 | 다른 약제 `CAUTION` / `BLOCKED` / `NEEDS_CHECK` | 제외 |
| A4 | 다른 약제 `OK`, `moa = None` | 제외 |
| A5 | 고른 약제 `moa = None`, 다른 약제 `OK` + `moa` 있음 | 포함 (`moa` 비교 생략) |
| S1 | 서비스: 병해충 지목, `BLOCKED`, 대안 0건 | `show_extension_office = true` |
| S2 | 서비스: 병해충 미지목, ③ `BLOCKED` (`history = 품목A 3건`) | `verdict = BLOCKED`, `show_extension_office = false`, `notices`에 「병해충을 지정하면 대안을 볼 수 있습니다」 |
| S3 | 서비스: 병해충 미지목, `verdict = NEEDS_CHECK` | `notices`에 「병해충을 지정하면 …」 없음 |
| RULE1 | `6_반복규칙` 규칙 표(§4 ④) | 표의 모든 대상에 대해 `rotation_rule()`이 위 표와 같은 값을 돌려준다 |
| MSG1 | §8 템플릿 전체 | 금지어(`추천 예측 예상 가능성 위험 확률 안전 문제없`)가 하나도 없음 |

## 10. 미결·확인 사항

1. **성분 단위 합산 여부.** 법령 기준이 품목 단위인지 성분 단위인지 확인되지 않았다. 성분 합산이 맞으면 품목 기준은 횟수를 적게 세어 **"가능"이 잘못 나온다** (위험한 쪽 오류). **출시 전에 농업기술센터·농약 등록 문서로 확인한다.** 엑셀 `3_`·`4_`에 성분 열이 없고 품목명만 있어, 성분 키를 만들려면 `5_약계열`의 품목명을 쪼개야 한다.
2. **다작용점 약제.** FRAC M(`카`) 계열은 `6_반복규칙`에 따라 ④에서 제한 없음으로 반영했다 (이전 미결 해소). 다만 ③ 횟수 제한은 그대로 적용한다.
3. **엑셀 데이터 검수 (S1).** 이전의 PSIS 샘플 조사를 대체한다.
   - `확인 필요` 7줄의 값 확정 (겹둥근무늬병 「수확7일」 1줄은 같은 약의 정상 줄이 있어 삭제 요청, 벼룩잎벌레 「파종(정식)일부터14일」 4줄, 노균병 「발생초기 + 3회」 1줄, 뿌리혹선충 「연1회」 1줄)
   - `계열 코드`가 없는 17줄과 `5_약계열`의 비어 있는 국내 코드 7줄 (④ `NEEDS_CHECK`)
   - 같은 (작물, 병해충, 약, 상표, 사용 방법, 희석배수)에 규칙이 둘인 줄 (주황 줄. §3의 「가장 엄격한 값」으로 처리)
   - 시연용 **배추·배추좀나방** 행 (PRD §4.3 시연 데이터)
4. **면책 문구.** "가능"이 사용 보증으로 읽히지 않게 하는 문구를 제품·법무와 정한다.
5. **별표 8 매핑표** → 엑셀 `5_약계열`의 국제 코드로 대체했다. 복합 계열(`카+가1` 등)의 `system`·`code`가 `5_`에 없어 「그 밖의 계열」로 취급된다 (§4 ④). 엑셀에서 복합 계열 성분을 확인한다.
6. **"읽지 못한 행이 하나라도 있으면 `NEEDS_CHECK`" 규칙(§3)의 영향.** 변환 구분 `확인 필요`가 7줄이라 영향이 작다. 7줄을 확정하면 거의 사라진다.
7. **사용 시기 조건 (PRD §6-4 "생육단계 등 추가 조건").** 판정은 수확 전 일수만 본다. 사용 방법 원문(`use_method`)은 근거로 보여 준다. 정식기·파종기 조건은 `AT_PLANTING`으로 별도 처리했다 (② `NEEDS_CHECK`). 「정식 후 N일」 같은 조건을 더 반영할지는 재검토한다.
8. **사용 방법 선택 (P1).** 지금은 사용 방법이 여럿이면 가장 엄격한 값을 쓴다 (예: 엑시렐 경엽처리 14일·3회 대 무인항공 21일·1회 → 21일·1회). 사용자가 사용 방법을 고르게 하려면 판정 요청에 `use_method`를 추가한다.
9. **`6_반복규칙`의 해석.** (a) 「살충제 전체: 연속 2회」와 「농약 전체: 최근 2번 중 연속 1회」가 살충제에는 둘 다 해당하는데, **IRAC(살충제)은 연속 2회, 그 밖은 연속 1회**로 읽었다. 팀 확인이 필요하다. (b) 「시즌 최대」와 「같은 세대(약 30일) 안」 조건은 판정에 반영하지 않았다.
