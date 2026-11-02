# 팜가디언 백엔드 API 명세

- 작성일: 2026-10-28
- 이 문서는 **프론트와 맺는 API 계약**이다. 엔드포인트 30개(아직 만들지 않은 `GET /zones/{id}/weather` 포함)의 요청·응답·오류를 한곳에 모았다.
- 근거: `팜가디언_아키텍처.md` §7(API 표·동작 규칙)·§8(외부 연동), `팜가디언_판정_규칙.md` §2(판정 타입). 판정 규칙의 세부는 judge_rules가 우선한다.
- 구현 후에는 FastAPI가 만든 `openapi.json`이 기준이 되고, 이 문서와 어긋나면 이 문서를 고친다.
- **【결정】** 표시는 이 문서를 쓰면서 새로 정한 값이다 (설계 문서에 없던 것). 프론트와 합의 때 확인한다.

## 0. BE 담당자

기준: `팜가디언_역할분담_일정.md`. 노션 명세 표의 「BE 담당자」 열과 같다.

| 담당 | API |
|---|---|
| 혜빈 (9) | `GET /addresses/search`, `GET /parcels`, `POST /fields`, `GET /fields`, `DELETE /fields/{id}`, `POST /fields/{id}/split-preview`, `POST /fields/{id}/zones`, `GET /zones/{id}`, `PATCH /zones/{id}` |
| 준혁 (21) | `POST /auth/signup`, `POST /auth/login`, `GET /me`, `POST /me/onboarding`, `DELETE /me`, `GET /crops`, `GET /zones/{id}/weather`, `GET /crops/{id}/symptom-parts`, `GET /pests/candidates`, `GET /pests`, `GET /pesticides`, `GET /zones/{id}/judgments/preview`, `POST /zones/{id}/judgments`, `POST /zones/{id}/sprays`, `GET /zones/{id}/sprays`, `DELETE /zones/{id}/sprays/{sid}`, `POST /zones/{id}/sprays/{sid}/restore`, `POST /ocr/pesticide-labels`, `POST /inventory`, `GET /inventory`, `DELETE /inventory/{drug_id}` |

`POST /auth/signup`은 준혁의 `identity`가 혜빈의 `field_service`를 호출해 첫 밭을 만든다.

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
| 상태 확인 | `GET /health` → `{"status": "ok"}`. 인증 없음. 엔드포인트 30개에 세지 않는다 |
| 압축 | 1,000바이트 이상 응답은 `Accept-Encoding: gzip` 요청에 gzip으로 보낸다 (판정 미리보기가 크다) |

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
| `UPSTREAM_ERROR` | 502 | 외부 API 실패 | `{source: "vworld"\|"farmmap"\|"kma"\|"anthropic", upstream_code?: string}` |
| `HTTP_ERROR` | 401·404 외 HTTP 상태 | 위 코드에 없는 HTTP 오류 (예: 허용되지 않는 메서드 405) | 없음 |

## 2. 공통 타입

```
Moa           {label_kr: string, system: string|null, code: string|null}
                  label_kr = 국내 계열 코드 (예 "라3"), system·code = 국제 코드 (예 "FRAC", "24"; `moa.json`의 `intl_code` 「FRAC 24」를 나눈 값)
Crop          {id: int, name: string}
Pesticide     {id: int, name: string, item_name: string, moa: Moa|null}
                  name = 상표명, item_name = 품목명
PesticideDetail  Pesticide + {company: string|null, form: string|null, ingredients: [string],
                  kind: "insecticide"|"fungicide"|"both"|null}
                  `GET /pesticides`, 판정 응답·대안·미리보기, 포장지 OCR 후보, `Spray.pesticide`가 쓴다.
                  form = 품목명의 마지막 단어 (예 「액상수화제」), kind = 살충·살균·겸용, company = 등록 행 중 첫 행의 제조사
                  ingredients = 유효 성분 이름 (복합제는 여럿). `ZoneSummary.last_spray.pesticide`는 계속 위 `Pesticide` 모양(4키)이다
Parcel        {farmmap_id: string, pnu: string, lnm: string, land_use: string, vdpt_yr: int|null,
               area_m2: number, geometry, matches_query: bool, used_by_field_id: int|null}
                  land_use = 논·밭·과수·시설. matches_query = 조회한 지번과 같은 필지인지
                  used_by_field_id = 이 사용자의 다른 밭이 쓰는 필지면 그 밭 id (X-User-Id가 없으면 항상 null)
Field         {id, name, address: string|null, area_m2, geometry, bbox, zones: [ZoneSummary]}      zones가 비면 아직 나누지 않은 밭
                  address = 밭을 만들 때 받은 주소 (지번). 보내지 않았거나 이 값을 넣기 전에 만든 밭은 null
Zone          {id, field_id, name, crop: Crop, planted_at: date|null, harvest_at: date|null, history_confirmed: bool,
               area_m2, geometry, bbox}
                  harvest_at = 수확 예정일. 없으면 null (판정 ②가 수확 가능일만 보여 준다)
ZoneSummary   {id, name, crop: Crop, planted_at: date|null, harvest_at: date|null, history_confirmed: bool, area_m2, geometry,
               last_spray: Spray|null, last_judgment: JudgmentBrief|null}
ZoneSpec      {name: string, crop_id: int, planted_at?: date}
SplitPiece    {geometry, area_m2}          순서 = 방향의 시작 쪽부터 (서→동, 조각이 남북으로 늘어서면 남→북), ratios 순서와 같다
Spray         {id: int, pesticide: PesticideDetail, pest: {id, name}|null, sprayed_on: date,
               source: "manual"|"app", cancelled: bool}
                  `ZoneSummary.last_spray`는 예전 4키 모양 {id, pesticide: Pesticide, sprayed_on, source}을 그대로 쓴다 (취소된 기록은 제외)
JudgmentBrief {judgment_id: int, created_at: datetime, pesticide: {id, name, item_name},
               pest: {id, name}|null, verdict: Verdict}                       【결정】
Verdict       "OK" | "CAUTION" | "BLOCKED" | "NEEDS_CHECK"        가능 / 주의 / 불가 / 확인 필요
Evidence      {source_text: string, data_asof: date}               원문이 비면 source_text = "없음"
CheckResult   {key: "registration"|"timing"|"count"|"moa", status: Verdict, message: string,
               facts: object, evidence: Evidence}                  facts 모양은 judge_rules §4
JudgeResult   {pesticide_id: int, moa: Moa|null, verdict: Verdict, checks: [CheckResult],
               notices: [string], data_asof: date}
                  checks는 항상 4개, 순서 registration → timing → count → moa. data_asof 표기는 "데이터 조회일"
Alternative   PesticideDetail과 같은 모양
JudgeResponse {judgment_id: int, apply_date: date, pesticide: PesticideDetail + {at_planting_only: bool}, result: JudgeResult,
               alternatives: [Alternative], show_extension_office: bool}
                  pesticide = 고른 약제 (`GET /pesticides` 항목과 같은 모양). 새로고침이나 OCR로 들어와 목록 자료가 없어도 약 정보를 그릴 수 있게 한다
PreviewItem   {pesticide: PesticideDetail, at_planting_only: bool, result: JudgeResult}
Rotation      {window_start: date|null, total: int, items: [{moa: Moa|null, count: int}]}
                  window_start가 null이면 정식일이 없어 전체 기록 기준. 비율은 프론트가 count/total
Weather       {issued_at: datetime, items: [{at: datetime, pty: int, pcp: string, pop: int|null}]}
                  앞으로 24시간, 시각별. pty = 강수형태 코드 (0 없음, 1 비, 2 비/눈, 3 눈, 4 소나기)
                  pcp = 1시간 강수량 원문 ("강수없음", "1mm 미만", "6.2mm", "30.0~50.0mm", "50.0mm 이상")
                  pop = 강수확률(%), 결측이면 null
PestCard      {id: int, name: string, kind: "병"|"해충"|null, photo_url: string|null, photo_source: string|null,
               description: string|null, occurrence: string|null, occurrence_source: string|null,
               vectors: [{id, name, guide, source}], months: [int], pesticide_count: int, is_virus: bool,
               carries: [{id, name}]}
                  months = 발생 월 (고른 발생 시기 행의 월, 자료가 없으면 빈 배열), pesticide_count = 이 작물×병해충에 등록된 약제 수 (없으면 0)
                  is_virus = 바이러스 병해충인지, carries = 이 벌레가 옮기는 바이러스 (이름순, 없으면 빈 배열)
                  이 작물의 도감 값 (정적 데이터 `pest`·`pest_photo`·`pest_season`, 없으면 null → 화면에 「없음」)
                  photo_source = 사진 출처 (작물명 "토마토", 대체 "양배추(대체)", 보충 "옥수수(보충)", 사진이 없으면 null)
                  description = 증상·피해. occurrence = 발생 시기 (발생 월·근거 문장), occurrence_source = 그 출처 (예 "NCPMS 설명", "PDF 경보")
                  vectors = 바이러스의 매개충 (`virus_vector.json`). name = 연결된 도감 병해충 이름, guide = 앱 안내 문구 (예 "이 벌레를 잡는 약으로 안내"), source = 근거.
                  자료가 없으면 빈 배열 → 「연결 자료 없음」
```

## 3. 인증·내 정보

### `POST /auth/signup` — 가입과 첫 밭 생성

- 요청 본문: `{username, password, field_name, parcel_farmmap_ids}`
  - `username` 3~30자, 영문·숫자·`_` **【결정】**
  - `password` 4~72자 **【결정】** (시연용, 복잡도 규칙 없음)
  - `field_name` 1~30자
  - `parcel_farmmap_ids` 문자열 1~20개, 중복 없음
- 응답 201: `{id: int, username: string, field: Field}`
- 오류: 409 `USERNAME_TAKEN`, 422 `VALIDATION_ERROR`(없는 `farmmap_id`면 `errors[].loc`가 `["body", "parcel_farmmap_ids", 순번]`, `type`은 `not_found` **【결정】**), 502 `UPSTREAM_ERROR`(`source: "farmmap"`; 이때 사용자도 만들어지지 않는다)
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

- 사용자와 밭·구역·기록·판정·창고를 모두 지운다. 응답 204. 이후 같은 `X-User-Id`는 401.

## 4. 참고 데이터

### `GET /crops`

- 응답 200: `[Crop]` (감자·배추·토마토)

### `GET /addresses/search` (인증 없음)

- 지번(필지) 검색이다. 건물이 없는 농지도 나온다. 브이월드 검색 API를 쓴다 (2026-10-29 변경: 도로명주소 API는 건물 있는 지번만 찾아 농지가 나오지 않았다).
- 쿼리: `keyword` (필수. 앞뒤 공백을 뺀 2~80자, 한글·숫자·공백·하이픈(`-`)만, 한글이 1자 이상), `page` (1~1000, 기본 1). 페이지당 10건 고정.
- 응답 200: `{total: int, items: [{jibun_addr: string, pnu: string}]}` — `jibun_addr`는 시도부터 쓴 지번 주소 (예 `경기도 가평군 청평면 청평리 161-3`), `pnu`는 19자리 문자열. 결과가 없으면 `{total: 0, items: []}`
- 같은 이름의 리가 여러 지역에서 나오면 사용자가 목록에서 고른다. 검색창 예시는 `청평리 161-3`처럼 지번까지 쓴다.
- 오류: 422 `VALIDATION_ERROR` (검색어·페이지 규칙 위반. 외부 API를 부르기 전에 거절한다), 502 `UPSTREAM_ERROR` (`source: "vworld"`)
- 검색어 글자 제한은 브이월드 방화벽이 따옴표·`<>` 같은 글자가 든 요청을 막기 때문이다.

### `GET /parcels` (인증 없음)

- 쿼리: `pnu` (필수, 19자리 숫자)
- 응답 200: `[Parcel]` — 그 지번과 **겹치는** 팜맵 필지 전체 (이웃 지번 필지 포함, 0건이면 빈 배열)
- 오류: 422 `VALIDATION_ERROR`, 502 `UPSTREAM_ERROR` (`source: "farmmap"`)

### `POST /ocr/pesticide-labels` — 포장지 OCR

- 포장지 사진에서 약제 후보를 찾는다. 판정 입구와 이력 입력 두 화면에서 부르며 날짜는 보내지 않는다. 아무것도 저장하지 않는다. 고르는 것은 사용자이고, 고른 `pesticide.id`를 `POST /zones/{id}/judgments`나 `POST /zones/{id}/sprays`의 `pesticide_id`에 그대로 쓴다.
- 요청: `multipart/form-data`, 필드 `image` (파일, 필수). jpeg·png·webp, 5MB(5 × 1024 × 1024바이트) 이하. 형식은 파일 내용으로 판단하고 `Content-Type` 값은 보지 않는다.
- 응답 200: `{candidates: [{pesticide: PesticideDetail, score: number, matched: ["brand"|"product"|"company"]}], read: {brand: string|null, product: string|null, company: string|null, text: string}}`
  - `candidates`: 0~5개, 점수가 높은 순. `pesticide`는 `GET /pesticides`와 같은 모양이고 `id`도 같다. `matched` = 읽은 값이 약제와 맞은 항목 (항상 brand, product, company 순). 상표명·품목명은 정규화한 유사도 0.9 이상, 제조사는 0.9 이상이거나 한쪽이 다른 쪽을 포함할 때(「경농」·「(주)경농」) 맞은 것으로 본다. 읽지 못한 항목은 맞지 않는다 **【결정】**. `score`와 순위는 `matched`와 무관하다. `score`는 0~1(소수 2자리)이며 정렬용이라 화면에 퍼센트로 보이지 않는다.
  - `read`: 모델이 포장지에서 읽은 내용 (`brand` 상표명, `product` 품목명, `company` 제조사). `text`는 읽은 글자 전체로 최대 2,000자이고, 읽지 못했으면 빈 문자열이다.
  - 읽지 못했거나 비슷한 약제가 없는 경우도 오류가 아니라 200이다 (`candidates: []`, `brand`·`product`·`company`는 null, `text`는 ""). 이때 프론트는 직접 검색으로 전환한다.
- 오류: 401, 422 `VALIDATION_ERROR` (`loc ["body", "image"]`: 파일 없음, 5MB 초과, 형식이 아님), 502 `UPSTREAM_ERROR` (`source: "anthropic"`: 인식 서비스 장애·시간 초과, 서버에 키가 없을 때)
- **【결정】** 요청·응답 모양 전체. 원 문서(`팜가디언_OCR_변경관련.md`)는 "이미지 파일 → 후보 목록 + 읽은 원문"까지만 정했고, 필드 이름·타입·오류는 백엔드가 정했다 (2026-11-01).

## 5. 밭과 구역

### `POST /fields` — 밭 추가

- 요청 본문: `{name: string(1~30자), parcel_farmmap_ids: [string](1~20개), address?: string}`
  - `address` **【결정】**: 프론트가 주소 검색에서 고른 `jibun_addr`. 앞뒤 공백을 뺀 1~200자이고, 빈 값이나 201자 이상은 422(`loc ["body","address"]`)다. 만든 뒤에는 고칠 수 없다.
- 응답 201: `Field` (`zones`는 빈 배열)
- 오류: 409 `PARCEL_ALREADY_USED`, 422, 502 (`source: "farmmap"`)

### `GET /fields`

- 응답 200: `[Field]` (밭별 구역 요약 `zones` 포함, 생성순)

### `DELETE /fields/{id}`

- 구역·기록·판정까지 지운다. 응답 204. 404.

### `POST /fields/{id}/split-preview` — 분할 미리보기 (저장 안 함)

- 요청 본문: `{direction: "crosswise"|"lengthwise", ratios: [int]}` — `ratios`는 1~10개, 각 값은 1~100의 정수. 균등 = `[1,1,1]`
- 응답 200: `[SplitPiece]` (`ratios`와 같은 길이)
- 오류: 404, 422

### `POST /fields/{id}/zones` — 구역 생성

- 요청 본문: `{direction, ratios, zones: [ZoneSpec]}` — `zones` 길이는 `ratios`와 같아야 한다. `name` 1~30자. `planted_at`은 오늘(KST) 이후 날짜 불가 (미래 정식일이면 ③ 횟수가 기록을 하나도 세지 않는다).
- 응답 201: `[Zone]` (분할 순서)
- 오류: 404, 409 `FIELD_ALREADY_SPLIT`, 422 (길이 불일치 등)
- 서버가 같은 입력으로 분할을 다시 계산한다 (결정적).

### `GET /zones/{id}`

- 응답 200: `Zone` + `{rotation: Rotation, recent_judgments: [JudgmentBrief]}` (최근 5건, 최신순)
- 오류: 404

### `PATCH /zones/{id}`

- 요청 본문 (모두 선택): `{name?: string, crop_id?: int, planted_at?: date|null, harvest_at?: date|null, history_confirmed?: bool}`
  - `planted_at: null`로 정식일을 비울 수 있다. 오늘(KST) 이후 날짜는 422.
  - `crop_id`가 바뀌면 `planted_at`은 요청 값, 없으면 null이 된다 (새 작기).
  - `planted_at` 값이 바뀌면 `history_confirmed`는 false가 된다 (같은 요청에서 명시하면 그 값).
  - `harvest_at` **【결정】**: 수확 예정일. `null`로 비울 수 있다. 정식일이 있으면 정식일과 같거나 그 이후여야 하고, 어기면 422다. 오늘보다 지난 날짜도 받는다 (판정에서 여유 일수가 음수로 나온다). `crop_id`가 바뀌면 같은 요청에 값이 없는 한 null이 된다 (새 작기). `planted_at`만 바뀌면 그대로 두되, 새 정식일이 수확 예정일보다 늦으면 422다. `history_confirmed`는 바꾸지 않는다.
  - 422의 `loc`: 요청에 `harvest_at`이 있으면 `["body","harvest_at"]`, 없으면 `["body","planted_at"]`.
  - 구역을 만들 때(`ZoneSpec`)는 받지 않는다. 새 구역은 null이다.
- 응답 200: `Zone`
- 오류: 404, 422

### `GET /zones/{id}/weather`

- 응답 200: `Weather`
- 오류: 404, 502 `UPSTREAM_ERROR` (`source: "kma"`). 판정과 무관하게 동작한다.

## 6. 병해충·약제

### `GET /crops/{id}/symptom-parts`

- 응답 200: `[string]` — 이 작물에 병해충이 연결된 증상 부위 (`덩이, 뿌리, 잎, 줄기, 벌레, 열매` 중, `pest.json`의 `parts` 값). **【결정】** 문자열 배열
- 오류: 404

### `GET /pests/candidates`

- 쿼리: `crop_id` (필수), `part` (필수, 증상 부위 목록의 값 중 하나)
- 응답 200: `[PestCard]` (이름순). 부위가 여러 개인 병해충은 하나만 맞아도 나온다.
- 오류: 404 (작물), 422 (`part` 값 오류)

### `GET /pests`

- 쿼리: `crop_id` (필수), `q` (선택, 이름 부분 일치)
- 응답 200: `[PestCard]` — 그 작물에 등록 약제가 있는 병해충, **또는 바이러스 병해충**(`virus_vector`에 바이러스로 있는 것, 등록 약제가 없어 `pesticide_count` = 0), 이름순. 도감에 없는 병해충도 나온다. 작물별 개수는 감자 25, 배추 45, 토마토 27 **【결정】**. 페이징 없음 **【결정】**
- 오류: 404

### `GET /pesticides`

- 쿼리: `crop_id` (필수), `pest_id` (선택. 없으면 그 작물 등록 약제 전체)
- 응답 200: `[PesticideDetail + {at_planting_only: bool}]` — 작용기작 → 품목명 → 상표명 순 **【결정】**. 페이징 없음 **【결정】**
  - `at_planting_only`: 이 작물(·병해충)의 등록 행이 모두 「심을 때」 사용 유형이면 true. 프론트가 「심을 때 쓰는 약」으로 묶어 보여준다 (judge_rules §3). 이 약은 판정에서 ②가 `NEEDS_CHECK`다.
- 오류: 404

## 7. 판정

### `GET /zones/{id}/judgments/preview` — 약제 목록 일괄 판정 (저장 안 함)

- 쿼리: `pest_id` (필수 **【결정】**: 병해충 없이 부르면 작물 전체 508~1,008개 약제를 판정해야 한다), `apply_date` (선택, `POST /judgments`와 같은 규칙)
- 응답 200: `[PreviewItem]` — `GET /pesticides`(이 작물×병해충)와 같은 약제 풀·같은 순서(작용기작 → 품목명 → 상표명). 항목마다 전체 `JudgeResult`가 있다.
- 아무것도 저장하지 않는다 (`judgment` 행도 만들지 않는다). 구역 정보와 살포 이력은 한 번만 읽고 약제마다 메모리에서 판정한다. 한 항목의 `result`는 같은 입력의 `POST /judgments` 결과와 같다.
- 풀 크기는 쌍마다 다르다 (91쌍, 중앙값 18, 최대 274). 프론트는 (구역, 병해충)마다 한 번 받아 홈·약 목록·대시보드에서 나눠 쓴다. 응답은 gzip이다.
- 오류: 401, 404 (남의 구역·없는 구역, 없는 병해충, 다른 작물의 병해충), 422 (`pest_id` 누락 `loc ["query","pest_id"]`, `apply_date`가 2100-12-31보다 늦음)

### `POST /zones/{id}/judgments`

- 요청 본문: `{pesticide_id: int, pest_id?: int, apply_date?: date}` — `pest_id`가 없으면 병해충 미지목
  - `apply_date` **【결정】**: 「이 날 살포한다면」의 날짜. 없으면 오늘(KST). 판정의 `today`로 쓰여 **수확 가능일(`harvest_from`)과 문구의 날짜**만 달라진다. 살포 이력은 날짜와 무관하게 구역의 전체 기록을 쓴다. 시연 날짜와 상관없이 같은 화면을 재현하려는 용도다 (판정만 하고 기록은 저장하지 않으므로 이력에 영향이 없다). 2100-12-31보다 늦은 날짜는 422다 (수확 가능일이 날짜 범위를 넘지 않게).
- 응답 201: `JudgeResponse` (판정을 저장한다). `apply_date`는 판정에 쓴 날짜(요청 값 또는 오늘)다.
  - `alternatives`는 병해충을 지목한 판정에만 계산한다 (같은 작물×병해충의 다른 약제 중 `OK`이고 작용기작이 다른 것). 지목하지 않았고 불가이면 `result.notices`에 안내 한 줄이 붙고 `alternatives`는 빈 배열.
  - `show_extension_office`: 「농업기술센터 문의」 안내를 보여줄지. 병해충을 지목했고 `verdict`가 `BLOCKED` 또는 `CAUTION`이며 대안이 0건일 때만 true (judge_rules §7)
- 오류: 404 (구역·약제·병해충이 없음), 422
- 그 작물·병해충에 **등록되지 않은 약제도 오류가 아니다.** 판정이 `BLOCKED`(①)로 나온다.

### `CheckResult.facts` (프론트가 쓰는 값)

자세한 규칙은 judge_rules §4. 값이 없으면 null이다.

| key | facts |
|---|---|
| `registration` | `{crop_registered, pest_specified, registered_pests: [string], rows: int, dilution: string|null}` (경우에 따라 일부만 있다. `dilution`은 등록 통과(`OK`) 때만 있고, 근거로 쓴 첫 등록 행의 희석 원문이다. 계산하지 않는다) |
| `timing` | `{phi_days: int|null, harvest_from: date|null, rows: int, strict_use_method: string|null, no_limit: bool}` + 구역에 수확 예정일이 있고 수확 전 일수를 알 때만 `{harvest_at: date, margin_days: int}` |
| `count` | `{used: int, max_uses: int|null, remaining: int, remaining_after: int|null, since: date, item_name: string, strict_use_method: string|null, no_limit: bool}` |
| `moa` | `{label: string, rule: "NO_LIMIT"|"CONSECUTIVE", max_consecutive: int|null, consecutive: int, unknown: int, window: [{id, sprayed_on, item_name, label: string|null}]}` |

## 8. 살포 기록

### `POST /zones/{id}/sprays`

- 요청 본문: `{pesticide_id: int, pest_id?: int|null, sprayed_on?: date, source: "manual"|"app", request_id: uuid, allow_duplicate?: bool}`
  - `pest_id` **【결정】**: 어떤 병해충에 쓴 기록인지. 없는 병해충 id는 422(`loc ["body","pest_id"]`)다. 존재만 확인하고 작물과의 일치는 보지 않는다.
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
  - **취소한 기록도 `cancelled: true`로 함께 나오고 `total`에도 센다.** 「올해 N회」처럼 세는 값은 프론트가 `cancelled`가 아닌 항목만 센다 **【결정】**.
- 오류: 404, 422

### `DELETE /zones/{id}/sprays/{sid}`

- 기록 취소. **행을 지우지 않고** 취소 시각만 남기는 소프트 취소다 (`GET`에 `cancelled: true`로 계속 나온다). 응답 204.
- 이미 취소한 기록을 다시 취소해도 204다 **【결정】**. 없는 기록이거나 다른 구역의 기록이면 404.
- 취소한 기록은 판정(③ 횟수·④ 연속 사용), 작용기작 요약, 중복 검사, `ZoneSummary.last_spray`에서 빠진다.

### `POST /zones/{id}/sprays/{sid}/restore`

- 취소한 기록을 되살린다. 응답 200 `Spray`. 없는 기록이거나 다른 구역의 기록이면 404. 취소하지 않은 기록에 불러도 200이다.
- 되살린 기록이 같은 날 같은 약제의 다른 기록과 겹쳐도 허용한다 **【결정】**.
- 같은 `request_id`로 `POST`를 다시 보내면, 그 사이 취소됐더라도 원래 기록을 `cancelled: true`로 돌려준다 **【결정】**.

### 창고 (내가 가진 약제)

판정이 「가능」이어도 그 약이 없으면 오늘 뿌릴 수 없다. 프론트는 창고에 있는 약에 배지를 달고 같은 판정 안에서 먼저 보여준다. 세 API 모두 `X-User-Id`가 필요하고 사용자마다 따로다. `drug_id`는 `Pesticide.id`(`pesticide_id`)와 같은 값이다. **【결정】** 요청은 `POST /inventory {drug_id}`, `DELETE /inventory/{drug_id}`, `GET /inventory → [drug_id, ...]`까지만 정했고, 응답 모양·순서·오류는 백엔드가 정했다 (2026-11-01).

#### `POST /inventory` — 창고에 담기

- 요청 본문: `{drug_id: int}`
- 응답: 처음 담으면 **201**, 이미 있으면 **200**. 본문은 같다 `{drug_id: int}` (재시도해도 안전하다).
- 오류: 401, 422 `VALIDATION_ERROR` (`loc ["body", "drug_id"]`: 누락·정수 아님·카탈로그에 없는 약제)

#### `GET /inventory`

- 응답 200: `[int]` — 약제 id를 담은 순서(오래된 것 먼저)로. 비어 있으면 `[]`. 약제 이름 등은 프론트가 이미 받은 약제 정보(`GET /pesticides`, 판정 대안, 포장지 OCR 후보)에 id로 연결한다.
- 오류: 401

#### `DELETE /inventory/{drug_id}` — 창고에서 빼기

- 응답 204. 오류: 401, 404 `NOT_FOUND` (창고에 없는 약제. 카탈로그에 없는 id도 404), 422 (`drug_id`가 정수가 아님)

## 9. 화면 흐름 (프론트 참고)

탭 4개: 홈, 병해충, 조회수정, 프로필. 첫 사용은 온보딩을 마쳐야 탭을 쓸 수 있다.

### 온보딩

1. 주소 검색 `GET /addresses/search` → 필지 선택 `GET /parcels` → `POST /auth/signup` (첫 밭이 생긴다).
2. 로그인한 사용자는 `GET /me`의 `onboarded`가 false면 온보딩으로 보낸다. 어디까지 했는지는 `GET /fields`(구역 유무, 구역별 `history_confirmed`)로 본다.
3. 구역 나누기(`split-preview` → `POST /fields/{id}/zones`) → 구역별 과거 살포 입력(`POST /zones/{id}/sprays`)·「누락 없음」(`PATCH`) → `POST /me/onboarding`.
4. 온보딩 뒤에도 밭 추가·삭제는 막지 않는다.

### 홈
- `GET /fields`: 밭별 구역과 상태 요약(`last_spray` + `last_judgment`, 기록이 없으면 「기록 없음」). 밭 추가는 온보딩의 필지 선택·구역 나누기 화면을 다시 쓴다.
- `GET /zones/{id}`: 편중도(`rotation`) + 최근 판정 5건. 이력은 `GET /zones/{id}/sprays`.

### 병해충 (판정)
1. 구역 선택.
2. 병해충 지목: `GET /crops/{id}/symptom-parts` → `GET /pests/candidates`, 또는 `GET /pests`(도감 목록·이름 검색). 바이러스면 `vectors`의 매개충을 고를 수 있고, 선택하지 않고 진행해도 된다.
3. 약제 선택: `GET /pesticides`.
4. `POST /zones/{id}/judgments` → 결과(체크 4개별 사유·근거 원문·데이터 조회일, 대안).
5. 날씨: 판정과 따로 `GET /zones/{id}/weather`. 실패하면 「날씨 조회 실패」만 표시하고 판정 화면은 그대로 둔다.
6. 「살포 기록 저장」: 저장 한 번에 `request_id`(UUID) 하나를 만들고 재시도에는 같은 값을 쓴다. 409 `DUPLICATE_SPRAY`면 「기존 기록 확인 / 실제 별도 살포로 저장 / 돌아가기」를 보여주고, 별도 살포면 `allow_duplicate: true`로 다시 보낸다.

### 조회수정
- 이력 목록·취소(취소 = 삭제), 과거 살포 추가 입력(판정을 거치지 않음).
- 구역 수정(`PATCH`): 이름·작물·정식일·「누락 없음」. 작물을 바꾸면 정식일을 새로 넣거나 비운다. 정식일이 바뀌면 백엔드가 「누락 없음」을 풀어 둔다.
- 밭 삭제: 구역·기록 포함. 잘못 고른 필지나 다시 나누기용이며 확인 화면이 필요하다.

### 프로필
- 공공데이터 출처·면책 안내, 로그아웃(저장한 id만 지움), 회원 탈퇴(`DELETE /me`, 확인 화면 필수).

## 10. 외부 API와의 대응 (참고)

| 우리 API | 외부 호출 |
|---|---|
| `/addresses/search` | 브이월드 검색 API (`req/search`, `category=parcel`). 결과 `id`가 PNU |
| `/parcels`, 밭 생성, 가입 | 팜맵 `getPnuBasedFarmmapInfo`, `getIdBasedFarmmapInfo` |
| `/zones/{id}/weather` | 기상청 단기예보 `getVilageFcst` |
| `/ocr/pesticide-labels` | Anthropic Messages API (`claude-haiku-5-5`). 모델은 글자만 읽고 약제 후보는 서버가 정적 JSON에서 고른다 |
| 병해충·약제·판정 | 요청 중 외부 호출 없음 (저장소의 정적 JSON `app/catalog/data`를 메모리로 읽음) |

외부 요청·응답의 상세는 `팜가디언_아키텍처.md` §8.
