# 팜가디언 백엔드 API 명세

- 작성일: 2026-10-28
- 이 문서는 **프론트와 맺는 API 계약**이다. 엔드포인트 24개의 요청·응답·오류를 한곳에 모았다.
- 근거: `farmguardian_architecture.md` §7(API 표·동작 규칙)·§8(외부 연동), `farmguardian_judge_rules.md` §2(판정 타입). 판정 규칙의 세부는 judge_rules가 우선한다.
- 구현 후에는 FastAPI가 만든 `openapi.json`이 기준이 되고, 이 문서와 어긋나면 이 문서를 고친다.
- **【결정】** 표시는 이 문서를 쓰면서 새로 정한 값이다 (설계 문서에 없던 것). 프론트와 합의 때 확인한다.

## 1. 공통

| 항목 | 규칙 |
|---|---|
| 형식 | JSON (UTF-8). 필드 이름은 `snake_case` |
| 사용자 식별 | `X-User-Id: {id}` 헤더 (정수). 없거나 없는 사용자면 401. **인증 없이 부르는 API 4개**: `POST /auth/signup`, `POST /auth/login`, `GET /addresses/search`, `GET /parcels` |
| 소유자 검사 | 남의 밭·구역·기록은 **404** `NOT_FOUND` |
| 날짜 | `date` = `YYYY-MM-DD`. "오늘"은 KST. 시각(`datetime`)은 `YYYY-MM-DDTHH:MM:SS+09:00` |
| 면적 | `area_m2` = 숫자(㎡). 팜맵 기준 **참고값**이며 지적 면적과 다를 수 있다 |
| 도형 | `geometry` = GeoJSON `MultiPolygon`, EPSG:5179 미터 좌표, y축이 위쪽, 소수 1자리. `bbox` = `[minx, miny, maxx, maxy]`. 프론트가 y축을 뒤집어 SVG로 그린다 |
| 목록 응답 | 배열을 그대로 돌려준다. 페이징이 있는 두 곳(`GET /addresses/search`, `GET /zones/{id}/sprays`)만 `{total, items}` **【결정】** |
| 삭제 | 성공하면 본문 없이 204 |

### 오류 응답

```
{"error": {"code": "NOT_FOUND", "message": "…", "details": {…}}}     details는 없을 수 있다
```

| code | HTTP | 언제 | `details` |
|---|---|---|---|
| `UNAUTHORIZED` | 401 | 헤더 없음·없는 사용자, 로그인 실패 | 없음 |
| `NOT_FOUND` | 404 | 없는 리소스, 남의 리소스 | 없음 |
| `USERNAME_TAKEN` | 409 | 가입 아이디 중복 | 없음 |
| `PARCEL_ALREADY_USED` | 409 | 같은 사용자의 다른 밭이 쓰는 필지 | `{farmmap_ids: [string]}` |
| `FIELD_ALREADY_SPLIT` | 409 | 이미 구역이 있는 밭에 구역 생성 | 없음 |
| `DUPLICATE_SPRAY` | 409 | 같은 구역·약제·날짜 기록 존재 | `{existing: Spray}` |
| `VALIDATION_ERROR` | 422 | 요청 값 오류 | `{errors: [{loc, msg, type}]}`. 입력값은 돌려주지 않는다 |
| `ONBOARDING_INCOMPLETE` | 422 | 구역이 없거나 「누락 없음」이 안 된 구역이 있음 | `{zone_count: int, unconfirmed_zone_ids: [int]}` **【결정】** |
| `UPSTREAM_ERROR` | 502 | 외부 API 실패 | `{source: "juso"\|"farmmap"\|"kma", upstream_code?: string}` |

## 2. 공통 타입

```
Moa           {label_kr: string, system: string|null, code: string|null}
                  label_kr = 국내 계열 코드 (예 "라3"), system·code = 국제 코드 (예 "FRAC", "24"; 엑셀 `5_약계열`의 「FRAC 24」를 나눈 값)
Crop          {id: int, name: string}
Pesticide     {id: int, name: string, item_name: string, moa: Moa|null}
                  name = 상표명, item_name = 품목명
Parcel        {farmmap_id: string, pnu: string, lnm: string, land_use: string, vdpt_yr: int|null,
               area_m2: number, geometry, matches_query: bool, used_by_field_id: int|null}
                  land_use = 논·밭·과수·시설. matches_query = 조회한 지번과 같은 필지인지
                  used_by_field_id = 이 사용자의 다른 밭이 쓰는 필지면 그 밭 id (X-User-Id가 없으면 항상 null)
Field         {id, name, area_m2, geometry, bbox, zones: [ZoneSummary]}      zones가 비면 아직 나누지 않은 밭
Zone          {id, field_id, name, crop: Crop, planted_at: date|null, history_confirmed: bool,
               area_m2, geometry, bbox}
ZoneSummary   {id, name, crop: Crop, planted_at: date|null, history_confirmed: bool, area_m2, geometry,
               last_spray: Spray|null, last_judgment: JudgmentBrief|null}
ZoneSpec      {name: string, crop_id: int, planted_at?: date}
SplitPiece    {geometry, area_m2}          순서 = 방향의 시작 쪽부터, ratios 순서와 같다
Spray         {id: int, pesticide: Pesticide, sprayed_on: date, source: "manual"|"app"}
JudgmentBrief {judgment_id: int, created_at: datetime, pesticide: {id, name, item_name},
               pest: {id, name}|null, verdict: Verdict}                       【결정】
Verdict       "OK" | "CAUTION" | "BLOCKED" | "NEEDS_CHECK"        가능 / 주의 / 불가 / 확인 필요
Evidence      {source_text: string, data_asof: date}               원문이 비면 source_text = "없음"
CheckResult   {key: "registration"|"timing"|"count"|"moa", status: Verdict, message: string,
               facts: object, evidence: Evidence}                  facts 모양은 judge_rules §4
JudgeResult   {pesticide_id: int, moa: Moa|null, verdict: Verdict, checks: [CheckResult],
               notices: [string], data_asof: date}
                  checks는 항상 4개, 순서 registration → timing → count → moa. data_asof 표기는 "데이터 조회일"
Alternative   {id: int, name: string, item_name: string, moa: Moa|null}      Pesticide와 같은 모양
JudgeResponse {judgment_id: int, result: JudgeResult, alternatives: [Alternative], show_extension_office: bool}
Rotation      {window_start: date|null, total: int, items: [{moa: Moa|null, count: int}]}
                  window_start가 null이면 정식일이 없어 전체 기록 기준. 비율은 프론트가 count/total
Weather       {issued_at: datetime, items: [{at: datetime, pty: int, pcp: string, pop: int|null}]}
                  앞으로 24시간, 시각별. pty = 강수형태 코드 (0 없음, 1 비, 2 비/눈, 3 눈, 4 소나기)
                  pcp = 1시간 강수량 원문 ("강수없음", "1mm 미만", "6.2mm", "30.0~50.0mm", "50.0mm 이상")
                  pop = 강수확률(%), 결측이면 null
PestCard      {id: int, name: string, kind: "병"|"해충"|null, photo_url: string|null, description: string|null,
               occurrence: string|null, source: string|null, vectors: [{id, name, source}]}
                  photo_url~source는 이 작물의 도감 값 (엑셀 `2_`·`1_`, 없으면 null → 화면에 「없음」)
                  vectors = 바이러스의 매개충 (자료가 없으면 빈 배열 → 「연결 자료 없음」)
```

## 3. 인증·내 정보

### `POST /auth/signup` — 가입과 첫 밭 생성

- 요청 본문: `{username, password, field_name, parcel_farmmap_ids}`
  - `username` 3~30자, 영문·숫자·`_` **【결정】**
  - `password` 4~72자 **【결정】** (시연용, 복잡도 규칙 없음)
  - `field_name` 1~30자
  - `parcel_farmmap_ids` 문자열 1~20개, 중복 없음
- 응답 201: `{id: int, username: string, field: Field}`
- 오류: 409 `USERNAME_TAKEN`, 422 `VALIDATION_ERROR`(없는 `farmmap_id`면 `details`에 그 id를 담는다 **【결정】**), 502 `UPSTREAM_ERROR`(`source: "farmmap"`; 이때 사용자도 만들어지지 않는다)
- 한 트랜잭션: 사용자 생성 → 필지 도형 조회(병렬, 동시 8개 이하) → 밭 저장.

### `POST /auth/login`

- 요청 본문: `{username, password}`
- 응답 200: `{id: int, username: string}`
- 오류: 401 `UNAUTHORIZED` (아이디 없음·비밀번호 틀림을 구분하지 않는다)

### `GET /me`

- 응답 200: `{id: int, username: string, onboarded: bool}` (`username` 추가 **【결정】**)

### `POST /me/onboarding`

- 요청 본문 없음. 구역이 1개 이상이고 모든 구역이 「누락 없음」일 때만 기록한다.
- 응답 200: `{id: int, onboarded: true}` (이미 완료여도 200, 멱등)
- 오류: 422 `ONBOARDING_INCOMPLETE`

### `DELETE /me`

- 사용자와 밭·구역·기록·판정을 모두 지운다. 응답 204. 이후 같은 `X-User-Id`는 401.

## 4. 참고 데이터

### `GET /crops`

- 응답 200: `[Crop]` (감자·배추·토마토)

### `GET /addresses/search` (인증 없음)

- 쿼리: `keyword` (필수, 2~80자), `page` (기본 1). 페이지당 10건 고정.
- 응답 200: `{total: int, items: [{road_addr: string, jibun_addr: string, pnu: string}]}` — `pnu`는 19자리 문자열
- 오류: 422 `VALIDATION_ERROR` (검색어 규칙 위반: 한 글자, 숫자만, 특수문자·SQL 예약어, 너무 긴 검색어, 시도명만, 결과 9천 건 초과. `details.source: "juso"`와 `upstream_code`를 담는다), 502 `UPSTREAM_ERROR` (`source: "juso"`)
- 검색어의 특수문자와 SQL 예약어는 **호출 전에** 거절한다 (외부 API가 서버 IP를 차단할 수 있다).

### `GET /parcels` (인증 없음)

- 쿼리: `pnu` (필수, 19자리 숫자)
- 응답 200: `[Parcel]` — 그 지번과 **겹치는** 팜맵 필지 전체 (이웃 지번 필지 포함, 0건이면 빈 배열)
- 오류: 422 `VALIDATION_ERROR`, 502 `UPSTREAM_ERROR` (`source: "farmmap"`)

## 5. 밭과 구역

### `POST /fields` — 밭 추가

- 요청 본문: `{name: string(1~30자), parcel_farmmap_ids: [string](1~20개)}`
- 응답 201: `Field` (`zones`는 빈 배열)
- 오류: 409 `PARCEL_ALREADY_USED`, 422, 502 (`source: "farmmap"`)

### `GET /fields`

- 응답 200: `[Field]` (밭별 구역 요약 `zones` 포함, 생성순)

### `DELETE /fields/{id}`

- 구역·기록·판정까지 지운다. 응답 204. 404.

### `POST /fields/{id}/split-preview` — 분할 미리보기 (저장 안 함)

- 요청 본문: `{direction: "crosswise"|"lengthwise", ratios: [int]}` — `ratios`는 1~10개, 각 값은 1 이상의 정수. 균등 = `[1,1,1]`
- 응답 200: `[SplitPiece]` (`ratios`와 같은 길이)
- 오류: 404, 422

### `POST /fields/{id}/zones` — 구역 생성

- 요청 본문: `{direction, ratios, zones: [ZoneSpec]}` — `zones` 길이는 `ratios`와 같아야 한다. `name` 1~30자.
- 응답 201: `[Zone]` (분할 순서)
- 오류: 404, 409 `FIELD_ALREADY_SPLIT`, 422 (길이 불일치 등)
- 서버가 같은 입력으로 분할을 다시 계산한다 (결정적).

### `GET /zones/{id}`

- 응답 200: `Zone` + `{rotation: Rotation, recent_judgments: [JudgmentBrief]}` (최근 5건, 최신순)
- 오류: 404

### `PATCH /zones/{id}`

- 요청 본문 (모두 선택): `{name?: string, crop_id?: int, planted_at?: date|null, history_confirmed?: bool}`
  - `planted_at: null`로 정식일을 비울 수 있다.
  - `crop_id`가 바뀌면 `planted_at`은 요청 값, 없으면 null이 된다 (새 작기).
  - `planted_at` 값이 바뀌면 `history_confirmed`는 false가 된다 (같은 요청에서 명시하면 그 값).
- 응답 200: `Zone`
- 오류: 404, 422

### `GET /zones/{id}/weather`

- 응답 200: `Weather`
- 오류: 404, 502 `UPSTREAM_ERROR` (`source: "kma"`). 판정과 무관하게 동작한다.

## 6. 병해충·약제

### `GET /crops/{id}/symptom-parts`

- 응답 200: `[string]` — 이 작물에 병해충이 연결된 증상 부위 (`덩이, 뿌리, 잎, 줄기, 벌레, 열매` 중, 엑셀 `2_병해충_도감`의 부위 값). **【결정】** 문자열 배열
- 오류: 404

### `GET /pests/candidates`

- 쿼리: `crop_id` (필수), `part` (필수, 증상 부위 목록의 값 중 하나)
- 응답 200: `[PestCard]` (이름순)
- 오류: 404 (작물), 422 (`part` 값 오류)

### `GET /pests`

- 쿼리: `crop_id` (필수), `q` (선택, 이름 부분 일치)
- 응답 200: `[PestCard]` — 그 작물에 등록된 병해충, 이름순. 도감에 없는 병해충도 나온다. 페이징 없음 **【결정】**
- 오류: 404

### `GET /pesticides`

- 쿼리: `crop_id` (필수), `pest_id` (선택. 없으면 그 작물 등록 약제 전체)
- 응답 200: `[Pesticide + {at_planting_only: bool}]` — 작용기작 → 품목명 → 상표명 순 **【결정】**. 페이징 없음 **【결정】**
  - `at_planting_only`: 이 작물(·병해충)의 등록 행이 모두 「심을 때」 사용 유형이면 true. 프론트가 「심을 때 쓰는 약」으로 묶어 보여준다 (judge_rules §3). 이 약은 판정에서 ②가 `NEEDS_CHECK`다.
- 오류: 404

## 7. 판정

### `POST /zones/{id}/judgments`

- 요청 본문: `{pesticide_id: int, pest_id?: int}` — `pest_id`가 없으면 병해충 미지목
- 응답 201: `JudgeResponse` (판정을 저장한다)
  - `alternatives`는 병해충을 지목한 판정에만 계산한다 (같은 작물×병해충의 다른 약제 중 `OK`이고 작용기작이 다른 것). 지목하지 않았고 불가이면 `result.notices`에 안내 한 줄이 붙고 `alternatives`는 빈 배열.
  - `show_extension_office`: 「농업기술센터 문의」 안내를 보여줄지. 병해충을 지목했고 `verdict`가 `BLOCKED` 또는 `CAUTION`이며 대안이 0건일 때만 true (judge_rules §7)
- 오류: 404 (구역·약제·병해충이 없음), 422

## 8. 살포 기록

### `POST /zones/{id}/sprays`

- 요청 본문: `{pesticide_id: int, sprayed_on?: date, source: "manual"|"app", request_id: uuid, allow_duplicate?: bool}`
  - `sprayed_on` 기본값 = 오늘(KST), **미래 날짜는 422**
  - `request_id`는 프론트가 「저장」 동작마다 만들고, 재시도에는 같은 값을 쓴다.
- 처리 순서:
  1. 같은 `request_id`가 **같은 구역**에 이미 있으면 그 기록을 **200**으로 돌려준다 (다시 저장하지 않음). 다른 구역·다른 사용자의 기록이면 기록을 보여주지 않고 **422** `VALIDATION_ERROR` **【결정】**.
  2. 같은 구역·`pesticide_id`·`sprayed_on` 기록이 있고 `allow_duplicate`가 true가 아니면 **409** `DUPLICATE_SPRAY` + `details.existing`. 별도 살포로 저장하려면 같은 `request_id`에 `allow_duplicate: true`를 붙여 다시 보낸다.
  3. 저장하고 **201** `Spray`.
- 오류: 404, 409, 422

### `GET /zones/{id}/sprays`

- 쿼리: `limit` (기본 20, 최대 100), `offset` (기본 0) **【결정】**
- 응답 200: `{total: int, items: [Spray]}` — `sprayed_on` 내림차순, 같으면 `id` 내림차순 **【결정】**
- 오류: 404, 422

### `DELETE /zones/{id}/sprays/{sid}`

- 기록 취소(삭제). 응답 204. 404.

## 9. 온보딩 흐름 (프론트 참고)

1. 주소 검색 `GET /addresses/search` → 필지 선택 `GET /parcels` → `POST /auth/signup` (첫 밭이 생긴다).
2. 로그인한 사용자는 `GET /me`의 `onboarded`가 false면 온보딩으로 보낸다. 어디까지 했는지는 `GET /fields`(구역 유무, 구역별 `history_confirmed`)로 본다.
3. 구역 나누기(`split-preview` → `POST /fields/{id}/zones`) → 구역별 과거 살포 입력(`POST /zones/{id}/sprays`)·「누락 없음」(`PATCH`) → `POST /me/onboarding`.
4. 온보딩 뒤에도 밭 추가·삭제는 막지 않는다.

## 10. 외부 API와의 대응 (참고)

| 우리 API | 외부 호출 |
|---|---|
| `/addresses/search` | 도로명주소 검색 API → `admCd`·`mtYn`·`lnbrMnnm`·`lnbrSlno`로 PNU 조립 |
| `/parcels`, 밭 생성, 가입 | 팜맵 `getPnuBasedFarmmapInfo`, `getIdBasedFarmmapInfo` |
| `/zones/{id}/weather` | 기상청 단기예보 `getVilageFcst` |
| 병해충·약제·판정 | 요청 중 외부 호출 없음 (엑셀 7개를 JSON으로 바꿔 미리 적재한 DB) |

외부 요청·응답의 상세는 `farmguardian_architecture.md` §8.
