# 팜가디언 백엔드 아키텍처 (개발 뼈대)

- 작성일: 2026-10-04 (판정 규칙·PSIS·팜맵 명세·구역 분할 반영 개정)
- 기준 문서: `farmguardian_flow_spec.md` (흐름 · 입출력), `farmguardian_judge_rules.md` (**판정 규칙 · 타입 · 문구 · 테스트 케이스**), `farmguardian_team_plan.md` (분담 · 일정), 농촌진흥청 `농약등록정보 Open API 기술명세서 (ver 1.0)`, 농림수산식품교육문화정보원 `팜맵 조회 Open API 활용가이드`
- 상태: 설계 승인됨. 문서 검토 대기
- 이 문서는 **S1 월~화 산출물(스키마, `judge()` 타입, API 계약)의 기준**이다. 판정 규칙의 세부는 `farmguardian_judge_rules.md`가 우선한다.

## 1. 목적과 범위

농가가 구역·병해충·약제를 고르면 4체크(①등록 ②시기 ③횟수 ④작용기작)로 사용 가능 여부(가능/주의/불가/확인 필요)를 알려주는 앱의 **백엔드**.

범위 안: 인증, 구역/필지(생성 시·사후 분할 포함), 병해충 후보, 약제 목록, 판정, 살포 기록·조회·수정, 외부 데이터 연동·적재.
범위 밖: 프론트엔드 설계, 배포 상세, 구역 삭제·병합(스펙에 없음), 알림.

## 2. 확정 결정

| 항목 | 결정 |
|---|---|
| DB | PostgreSQL + **PostGIS**. 필지 도형은 `geometry(MultiPolygon, 5179)` |
| 면적 | `ST_Area` (SRID 5179가 미터 평면이므로 결과가 ㎡). 스펙 §4의 신발끈 공식을 대체. **팜맵 기준 참고값**이며 지적 면적과 다를 수 있다 |
| 로그인 | **카카오 소셜 로그인.** 사용자 식별은 카카오 회원번호만 저장 (동의항목 없음) |
| 세션 | 백엔드가 발급하는 JWT 하나 (HS256). refresh 토큰 없음, 만료는 길게 |
| 프레임워크 | FastAPI, **동기** 엔드포인트 |
| DB 접근 | SQLAlchemy 2.0 (동기) + GeoAlchemy2 + Alembic |
| 코드 구조 | **기능별 모듈 + 판정 코어 격리** (§4) |
| 판정 모델 | Pydantic 모델 하나를 `judge()` 입출력과 API 응답에 공통 사용 |
| 지도 | 사용 안 함. 폴리곤 좌표를 내려주고 프론트가 SVG로 렌더링 |
| ② 시기 | 수확 예정일 입력 없음. "오늘 살포하면 N월 N일부터 수확 가능"을 계산해 표시 (`BLOCKED` 없음) |
| ③ 집계 단위 | **품목명(`item_name`) 기준 합산.** 성분 단위는 미확인 (judge_rules §10-1) |
| 편중도 | 작기 전체 비율 (④ 판정의 최근 3회 창과 별개) |
| 약제 원천 | PSIS 목록 API(`SVC01`) 한 번으로 행 단위 전부 적재 (§8). 갱신일을 주지 않으므로 `data_asof` = 적재일 |
| 팜맵 필지 | 팜맵 조회 Open API(공공데이터포털). 구역의 필지 단위는 **팜맵 필지(`fmapInnb`)** 이지 지번이 아니다. 한 지번이 여러 필지일 수 있고 PNU 조회는 이웃 지번과 겹치는 필지까지 돌려준다. 법적 효력 없는 참고 자료 |
| 구역 분할 | **필지 단위**(도형은 자르지 않음). 생성 시 `POST /zones/batch`, 사후 `POST /zones/{id}/split`. 필지는 사용자당 한 구역에만 속함. 사후 분할 시 **이력은 모든 새 구역에 복사** |

## 3. 시스템 구성

```
프론트(SPA) ── HTTPS/JSON, Bearer JWT ──▶ FastAPI (app/)
                                            │
        ┌────────────┬──────────────┬───────┴──────┬──────────────┐
      auth/        zones/        judge/         records/       pests/
                  integrations/                                    │
                      │                                            │
         도로명주소 · 팜맵 · 카카오 (요청 시 호출)        PostgreSQL + PostGIS
                                                                   ▲
                                      PSIS · NCPMS ── ingest (수동 실행) ──┘
```

## 4. 코드 구조

```
app/
  core/          설정, DB 세션, JWT, 에러 형식, 공통 의존성, today_kst()
  auth/          카카오 로그인, users                         (팀장)
  zones/         구역 생성·batch·수동·필지 교체·분할 (write.py, 팀원) / 목록·상세·속성 수정 (read.py, 팀장)
  integrations/  juso.py, pnu.py, farmmap.py (GML 파서 포함)   (팀원)
  ingest/        PSIS·NCPMS 적재, PSIS 문자열 파서             (팀장)
  pests/         증상 부위, 병해충 후보                        (팀장)
  judge/         schemas.py, rules.py(순수), service.py, router.py   (팀장)
  records/       spray_log, 조회, 수정, 이력 복사                (팀장)
migrations/
tests/
openapi.json
```

기능 폴더마다 `router.py / service.py / models.py / schemas.py`를 둔다.

규칙:
- `judge/schemas.py`와 `judge/rules.py`는 DB·HTTP를 임포트하지 않는다 (순수).
- 다른 기능 모듈은 `service`만 임포트한다. 남의 `models`를 직접 쓰지 않는다. 예: 구역 상세의 편중도는 `judge.service`가 감싼 `rotation_summary`를 호출하고, 구역 사후 분할은 `records.service.copy_history`로 이력을 복사한다.
- 폴더가 담당자 경계다. 경계를 넘는 수정은 상대 리뷰를 받는다. `zones/`만 파일로 나눈다 (`write.py` 팀원, `read.py` 팀장). 라우터는 서로의 `service` 함수를 호출한다.

## 5. DB 스키마

PSIS·팜맵 필드와의 대응을 괄호로 표시한다.

```
users(id, provider, provider_uid, created_at)              UNIQUE(provider, provider_uid)
crop(id, name, is_perennial, ext_code)                     ext_code = cropCd. UNIQUE(ext_code)
pest(id, name, kind NULL, ncpms_code NULL, photo_url NULL) name = diseaseWeedName. UNIQUE(name)
pest_symptom(pest_id, crop_id, part)                       PK 3개. 증상 부위 → 후보
moa(id, label_kr, system NULL, code NULL)                  label_kr = indictSymbl (예: 라3). UNIQUE(label_kr)
                                                           system/code = FRAC·IRAC (별표 8 매핑으로 채움)
pesticide(id, psis_code, name, item_name, company,
          ingredient_en, use_name, moa_id NULL)            psis_code = pestiCode. UNIQUE(psis_code)
                                                           name = pestiBrandName, item_name = pestiKorName,
                                                           ingredient_en = engName, use_name = useName
registration(id, crop_id, pest_id, pesticide_id, psis_use_seq,
             phi_days NULL, max_uses NULL,
             use_suittime_raw, use_num_raw, dilut_raw, use_timing_raw,
             loaded_at)                                    psis_use_seq = diseaseUseSeq
                                                           UNIQUE(pesticide_id, psis_use_seq)
                                                           CHECK phi_days >= 0, max_uses > 0
zone(id, user_id, name, crop_id, planted_at,
     manual_area_m2 NULL, manual_width_m NULL, manual_height_m NULL,
     no_prior_spray bool default false)
zone_parcel(id, zone_id, user_id, farmmap_id, pnu, lnm, land_use, vdpt_yr,
            geom geometry(MultiPolygon, 5179), fetched_at) UNIQUE(user_id, farmmap_id)
                                                           farmmap_id = fmapInnb, pnu = pnuLnmCd,
                                                           lnm = 지번 표기 (예: 161-7 전),
                                                           land_use = intprNm (논·밭·과수·시설),
                                                           vdpt_yr = vdptYr (영상촬영년도)
                                                           user_id는 zone.user_id의 복사본 (서비스가 일치시킨다)
spray_log(id, zone_id, pesticide_id, sprayed_on, source)   source = 'manual' | 'app'
judgment(id, zone_id, pest_id NULL, pesticide_id, verdict,
         result jsonb, created_at)
```

인덱스: `spray_log(zone_id, sprayed_on DESC)`, `judgment(zone_id, created_at DESC)`, `registration(crop_id, pesticide_id)`, `registration(crop_id, pest_id)`, `pesticide(item_name)`, `zone_parcel(zone_id)`. 공간 검색이 없으므로 공간 인덱스는 만들지 않는다.

규칙이 스키마에 붙는 방식 (세부 판정은 judge_rules):
- ①등록 = `registration` 행 존재. ②③ 값 = `phi_days`, `max_uses`. 병해충 미지목이면 고른 상표의 작물 행 전체에서 가장 엄격한 값. **PSIS가 준 문자열을 못 읽은 행은 값이 NULL**이고 원문 컬럼에 남아 있어 `NEEDS_CHECK`와 근거 표시에 쓴다.
- ③ 횟수 = `spray_log`를 `pesticide.item_name`으로 조인해 **같은 품목명**이고 창(일년생 `planted_at` / 다년생 올해 1/1) 안인 건수. 작물을 바꾸면 `planted_at`을 갱신하므로 0부터 다시 센다. **작기 테이블은 두지 않는다.**
- ④ = 구역 이력 최근 3건의 약제 → `moa.label_kr` 비교.
- 구역 면적 = 필지가 있으면 `ST_Area(geom)` 합, 없으면 `manual_area_m2`. 가로×세로 입력은 저장 시 `manual_area_m2 = 가로 × 세로`로 변환하고 가로·세로도 함께 보관한다 (개략 배치도용).
- 필지 도형은 구역 등록(또는 필지 연결) 시 팜맵에서 **1회** 받아 저장한다 (스펙 §1). 새로 들어온 필지만 받고, 이미 저장된 필지를 다른 구역으로 옮길 때는 다시 받지 않는다.
- **필지는 사용자당 한 구역에만 속한다** (`UNIQUE(user_id, farmmap_id)`). 구역 분할도 이 제약 위에서 필지를 나누는 것이다.
- 팜맵은 지적도가 아니라 실제 경작 구획을 판독한 지도이고 법적 효력이 없다. 면적·경계는 참고값이다.
- 판정은 호출마다 `judgment`에 저장한다. `result`에 근거 원문·기준일 스냅샷이 들어 있어 데이터가 바뀌어도 당시 화면을 재현할 수 있다.
- 「뿌린 적 없음」 = `zone.no_prior_spray`.
- `registration.loaded_at`의 날짜가 `data_asof`다. 화면에서는 "데이터 조회일"로 표기한다 (PSIS가 갱신일을 주지 않음).
- 병해충은 PSIS에 코드가 없고 이름 문자열뿐이다. `pest.name`을 PSIS 이름으로 만들고 NCPMS 연결(`ncpms_code`, 사진, 증상 부위)은 별도 매칭으로 채운다.

## 6. `judge()` 타입

전체 정의, 규칙, 문구, 테스트 케이스는 **`farmguardian_judge_rules.md`** 를 따른다. 여기에는 구조의 요약만 둔다.

```python
Verdict: OK, CAUTION, BLOCKED, NEEDS_CHECK       # 가능 / 주의 / 불가 / 확인 필요
JudgeInput:  today, is_perennial, planted_at, no_prior_spray, pest_id | None,
             pesticide_id, item_name, moa | None,
             registrations (고른 상표의 이 작물 행 전부), history (구역 전체 이력)
CheckResult: key (registration|timing|count|moa), status, message, facts, evidence | None
JudgeResult: pesticide_id, moa, verdict, checks (항상 4개), notices: list[str], data_asof

judge(inp) -> JudgeResult
window_start(today, is_perennial, planted_at) -> date
rotation_summary(history, today, is_perennial, planted_at) -> RotationSummary
pick_alternatives(selected, others) -> list[JudgeResult]       # 필터만. 이름 채움·정렬은 서비스
```

설계 근거:
- **체크 4개를 항상 반환**한다. 프론트가 4체크 목록을 고정 렌더링한다. 체크 상태는 `Verdict`를 재사용하고 최종 `verdict`는 최고 우선순위 하나.
- **`message`(한글 사유 문장)와 `notices`는 백엔드가 생성**한다. "예측·추천 표현 금지" 규칙을 한 곳에서 테스트하기 위해서다. 프론트는 색과 아이콘만 담당한다.
- **`facts` 키는 체크별로 문서에 고정**한다. dict라 타입은 약하지만 1달 일정에 맞춘 선택이다.
- **대안은 `judge()` 밖에서 만든다.** 서비스가 같은 작물×병해충의 다른 약제들도 `judge()`로 돌려 `pick_alternatives`에 넘긴다.
- 「농업기술센터 문의」는 API 응답 필드(`show_extension_office`)이며 병해충을 지목했고 불가·주의에 대안이 0건일 때만 true다.

## 7. API

모든 엔드포인트는 JWT가 필요하다 (`/auth/kakao`만 예외). `/zones/{id}/*`는 소유자 검사를 하고 남의 구역은 **404**를 돌려준다.

| 메서드 경로 | 용도 | 요청 → 응답 핵심 | 모듈 |
|---|---|---|---|
| `POST /auth/kakao` | 로그인 | `{code, redirect_uri}` → `{access_token}` | auth |
| `GET /crops` | 작물 목록 | → `[{id, name, is_perennial}]` | zones |
| `GET /addresses/search` | 주소 검색 | `?keyword&page` → `[{road_addr, jibun_addr, pnu}]` | integrations |
| `GET /parcels` | 주소와 겹치는 팜맵 필지 조회 | `?pnu` → `[Parcel]` (선택 화면용 폴리곤, 이웃 지번 필지 포함) | integrations |
| `POST /zones` | 구역 생성 | `ZoneSpec` → `Zone` | zones |
| `POST /zones/batch` | 구역 여러 개 생성 (생성 시 분할) | `{zones: [ZoneSpec]}` → `[Zone]` | zones |
| `GET /zones` | 구역 목록 | → `[ZoneSummary]` | zones |
| `GET /zones/{id}` | 구역 상세 | → `Zone` + `rotation` + `recent_judgments` | zones, records |
| `PATCH /zones/{id}` | 구역 수정 | `{name?, crop_id?, planted_at?, no_prior_spray?, parcel_farmmap_ids?, manual?}` | zones |
| `POST /zones/{id}/split` | 구역 사후 분할 | `SplitRequest` → `{zone, created}` | zones |
| `GET /crops/{id}/symptom-parts` | 증상 부위 목록 | → `[part]` | pests |
| `GET /pests/candidates` | 병해충 후보 | `?crop_id&part` → `[{id, name, kind, photo_url}]` | pests |
| `GET /pesticides` | 등록 약제 목록 | `?crop_id&pest_id?` → `[{id, name, item_name, moa}]` | judge |
| `POST /zones/{id}/judgments` | 판정 | `{pesticide_id, pest_id?}` → `JudgeResponse` (저장함) | judge |
| `POST /zones/{id}/sprays` | 기록 (「이 약 쓸게요」, 과거 이력) | `{pesticide_id, sprayed_on?, source}` → `Spray` | records |
| `GET /zones/{id}/sprays` | 이력 | `?limit&offset` → `[Spray]` | records |
| `PATCH /zones/{id}/sprays/{sid}` | 이력 수정 | `{pesticide_id?, sprayed_on?}` | records |
| `DELETE /zones/{id}/sprays/{sid}` | 이력 삭제 / 기록 취소 | - | records |

공통 응답 모양:

```
Parcel        {farmmap_id, pnu, lnm, land_use, vdpt_yr, area_m2, geometry,
               matches_query?, used_by_zone_id?}
              geometry = GeoJSON MultiPolygon, EPSG:5179 미터, y축 위쪽, 소수 1자리
              matches_query (조회한 지번과 같은 필지인지), used_by_zone_id (이 사용자의 다른 구역이
              이미 쓰는 필지면 그 구역 id)는 GET /parcels 응답에만 있다
Zone          {id, name, crop, planted_at, no_prior_spray, area_m2, is_manual,
               manual: {width_m, height_m} | null, parcels: [Parcel],
               bbox: [minx, miny, maxx, maxy] | null}
ZoneSummary   {id, name, crop, area_m2, is_manual, last_spray, last_judgment}
Spray         {id, pesticide: {id, name, item_name, moa}, sprayed_on, source}
Alternative   {pesticide_id, name, item_name, moa}
JudgeResponse {judgment_id, result: JudgeResult, alternatives: [Alternative],
               show_extension_office: bool}
rotation      {window_start, total, items: [{moa | null, count}]}
              예: {2026-05-01, 7, [{가1, 4}, {나2, 2}, {null, 1}]}. 비율은 프론트가 count/total
ZoneSpec      {name, crop_id, planted_at, parcel_farmmap_ids[] | manual}
SplitRequest  {parts: [SplitPart], keep_index: 0}
SplitPart     {name?, crop_id?, planted_at?, parcel_farmmap_ids[] | manual}
```

동작 규칙:
- **작물 변경 = 새 작기.** `PATCH`에서 `crop_id`가 바뀌면 `planted_at`이 필수다. 없으면 422 + `PLANTED_AT_REQUIRED`. 프론트가 정식일을 다시 묻는다.
- **`PATCH`의 `parcel_farmmap_ids`는 목록 전체를 교체한다.** 목록에서 빠진 필지는 구역에서 풀리고, 새로 들어온 필지만 팜맵에서 받는다. 필지가 하나도 안 남는데 `manual`도 없으면 422. 수동 구역에 필지를 나중에 연결할 때도 같은 방식이고, 필지가 생기면 면적은 `ST_Area` 합으로 바뀐다.
- **폴리곤 좌표:** 프론트가 y축을 뒤집어 SVG로 그린다. 수동 구역은 `parcels`가 비고 `bbox`가 null이며 `manual`의 가로×세로로 개략 배치도를 그린다.
- **살포일:** 미래 날짜는 422로 거부한다 (횟수 창이 꼬이는 것을 막음). 기본값은 `today_kst()`.
- **편중도(`rotation`):** 창은 ③과 같은 작기이고 살포 **건수** 기준이다 (④ 판정과 별개).
- **대안:** 병해충을 지목한 판정에만 계산한다. 지목하지 않았고 불가·주의이면 `result.notices`에 안내 한 줄이 붙고 `alternatives`는 빈 목록이다. 정렬은 작용기작 → 품목명 → 상표명.
- **약제 목록:** 같은 품목의 상표가 여럿이라 길 수 있다. 묶어서 보여주는 방법은 프론트와 정한다.
- `recent_judgments`는 최근 5건.

### 구역 분할

팜맵이 이미 필지를 구획해 두었으므로 **도형을 자르지 않고 필지를 묶음별로 나눈다.**

**생성 시 (`POST /zones/batch`)**
- 요청의 `zones`(최대 20개)를 한 트랜잭션으로 만든다. 구역 하나만 만드는 `POST /zones`도 같은 서비스 함수를 쓴다.
- 요청 안에서 같은 `farmmap_id`가 둘 이상의 구역에 들어 있으면 422.
- 이 사용자의 다른 구역이 이미 쓰는 필지가 있으면 409 `PARCEL_ALREADY_USED` (`details.farmmap_ids`).
- 필지는 구역마다 따로 조회하지 않고 **스레드 풀로 병렬 조회**한다 (평균 600ms × n 직렬 방지).

**사후 (`POST /zones/{id}/split`)**
- `parts`는 2개 이상 20개 이하다. `keep_index`번째 부분이 **원래 구역을 이어받고**(같은 `id`, 같은 `judgment` 기록) 나머지는 새 구역이 된다.
- `name`은 새 구역에서 필수이고 이어받는 구역은 생략하면 그대로다. `crop_id`·`planted_at`을 생략하면 원래 구역 값을 물려받는다. `crop_id`를 바꾸면 `planted_at`이 필수다 (`PLANTED_AT_REQUIRED`).
- **필지 구역은 분할이 파티션이어야 한다.** 모든 부분의 `parcel_farmmap_ids` 합집합이 원래 구역의 필지와 정확히 같고, 서로 겹치지 않으며, 각 부분이 비어 있지 않다. 어긋나면 422 + `details.missing / extra / duplicated`. 필지는 도형을 다시 받지 않고 `zone_parcel.zone_id`만 바꾼다.
- **수동 구역**이면 각 부분이 `manual`(면적 또는 가로×세로)을 가진다.
- **이력은 모든 새 구역에 복사한다.** 분할 전 살포는 모든 필지에 같이 이뤄졌으므로 새 구역 각각이 같은 이력을 가져야 ③ 횟수가 적게 세어지지 않는다. 이력을 나눠 가지면 횟수를 적게 세어 "가능"이 잘못 나오는 위험한 방향이라 복사가 안전하다. `spray_log`는 날짜·약제·`source`를 그대로 복사하고 `no_prior_spray`도 복사한다. 판정 기록(`judgment`)은 복사하지 않는다 (이어받는 구역에 남는다).
- 복사는 `records.service.copy_history(from_zone_id, to_zone_id)`가 한다. 복사한 이력은 이후 구역별로 독립적으로 수정·삭제된다.
- 작물이 바뀐 부분도 이력을 그대로 복사한다. ③은 창(`planted_at`)이, ④는 작기와 무관하게 최근 3건을 보므로 규칙이 알아서 처리한다.
- **병합은 범위 밖이다.** 필지를 `PATCH`로 다른 구역에 옮길 수는 있지만 이력은 따라가지 않는다.

## 8. 외부 연동

| 연동 | 파일 | 함수 | 비고 |
|---|---|---|---|
| 도로명주소 | `integrations/juso.py` | `search(keyword, page)` | 승인키는 서버 전용 |
| PNU 조립 | `integrations/pnu.py` | `assemble_pnu(admCd, lnbrMnnm, lnbrSlno, mtYn)` | **순수 함수**, 스펙 §2 공식 |
| 팜맵 | `integrations/farmmap.py` | `parcels_by_pnu(pnu)`, `parcel_by_id(id)`, `parse_farmmap_response(xml)`(순수) | 공공데이터포털 `serviceKey`. 아래 상세 |
| 카카오 | `auth/kakao.py` | `exchange_code()`, `fetch_user_id()` | |
| PSIS | `ingest/psis.py` | `python -m app.ingest.psis` | 수동 실행, cron은 나중 |
| NCPMS | `ingest/ncpms.py` | `python -m app.ingest.ncpms` | 1회 적재로 시작 |

- 공통: `httpx` 동기 클라이언트, 타임아웃 5초, 재시도 없음. 실패는 **502 `UPSTREAM_ERROR`** + `details.source`.
- 카카오 흐름: 프론트가 `code`를 받아 `POST /auth/kakao`로 전달 → 백엔드가 토큰 교환과 `GET /v2/user/me` 호출 → `users` upsert → JWT 발급. REST API 키는 서버에만 둔다.
- 테스트: `httpx.MockTransport`로 가짜 응답을 쓴다. **PSIS·팜맵 명세서의 예시 응답을 fixture로 저장**하고, S1 조사에서 받은 실제 응답을 더해 재사용한다.

### 팜맵 조회 (`integrations/farmmap.py`)

명세서(`getFarmmapService`, 갱신주기 연 1회) 기준:
- 호출: `GET http://apis.data.go.kr/B552895/getFarmmapService/{기능}?serviceKey=…&type=xml&…`. 키는 공공데이터포털에서 활용신청해 발급받고 URL 인코딩해서 보낸다.
- 쓰는 기능은 둘이다. `getPnuBasedFarmmapInfo?pnuCode=` → `parcels_by_pnu`, `getIdBasedFarmmapInfo?id=` → `parcel_by_id`. 좌표·반경 기반 조회와 `getIdbasedLandRegisterInfo`(팜맵 필지와 겹치는 지번 목록)는 쓰지 않는다.
- **PNU 조회는 "그 지번과 중첩되는 팜맵 필지 전체"를 돌려준다.** 명세서 예시에서 지번 하나로 7개가 왔고 이웃 지번 필지가 섞여 있었다. 한 지번이 판독이 다른 필지 여러 개로 쪼개져 있기도 하고, 필지 하나가 여러 지번과 겹치기도 한다. 그래서 `Parcel.matches_query`(필지의 `pnuLnmCd`가 조회한 PNU와 같은지), `lnm`, `land_use`를 내려줘 프론트가 구분해 보여준다. **구역의 단위는 지번이 아니라 팜맵 필지다.**
- 응답 XML의 `fmapBdcrd`는 GML `MultiPolygon`(`srsName="EPSG:5179"`)이다. `gml:coordinates`의 `x,y x,y …`를 파싱해 WKT로 만들고 `ST_GeomFromText(wkt, 5179)`로 저장한다. 파서는 순수 함수 `parse_farmmap_response(xml) -> list[FarmmapParcel]`로 만들고 **명세서 예시 XML로 테스트**한다 (키 없이 가능). 외곽(`outerBoundaryIs`)뿐 아니라 구멍(`innerBoundaryIs`)도 처리한다. 명세서 예시에는 구멍이 없어서 실제 응답에서 확인한다.
- 필드 대응: `fmapInnb` → `farmmap_id`, `pnuLnmCd` → `pnu`, `lnm` → `lnm`, `intprNm` → `land_use`(논·밭·과수·시설), `vdptYr` → `vdpt_yr`.
- 오류: `resultCode`가 `00`이 아니면 502 `UPSTREAM_ERROR`. 오류코드 22(요청 제한 초과), 30·31(키 미등록·만료), 32(등록되지 않은 IP)는 `details.upstream_code`에 담는다.
- **서비스가 HTTP(SSL 없음)이고 키가 URL에 실린다.** 서버 간 호출로만 쓰고 요청 URL(키 포함)을 로그에 남기지 않는다 (`httpx` 로그 레벨 주의). 오류코드 32가 있으므로 **서버의 고정 출력 IP 등록이 필요한지** 키 신청 때 확인한다.
- **팜맵은 지적도가 아니며 법적 효력이 없다** (명세서 §2). 면적과 경계는 참고값이므로 화면에 그렇게 표시해야 한다 (§10).
- 응답은 평균 600ms, 초당 50건 제한이다. 필지 조회는 병렬로 하되 동시에 8개 이하로 제한한다.

### PSIS 적재 (`ingest/psis.py`)

매뉴얼(ver 1.0) 기준:
- 호출: `GET https://psis.rda.go.kr/openApi/service.do?apiKey=…&serviceCode=SVC01&serviceType=AA001&startPoint={페이지}&displayCount={≤99}&cropName=…&cropCheck=Y`. 인증 파라미터는 `apiKey`다 (매뉴얼 본문의 `serviceKey` 표기와 다름. 예시 URL을 따른다).
- 응답은 **XML**. 표준 라이브러리 `xml.etree.ElementTree`로 파싱한다.
- 제한: 초당 10건 이하. 호출 사이에 약 0.15초 간격을 둔다. 에러는 `errorCode`(`ERR_101` 인증 실패, `ERR_201` 파라미터 오류, `ERR_901` 서버 오류 등)로 온다.
- **지원 작물만 적재**한다. `cropName`(최대 4개)과 `cropCheck=Y`로 작물별로 페이지를 돈다.
- 상세 API(`SVC02`)는 쓰지 않는다. 목록 응답 예시에 `useSuittime`, `useNum`, `dilutUnit`, `pestiUse`가 이미 있다. **실제 응답에 있는지 S1 샘플 조사에서 확인**한다.
- 매핑: `pestiCode` → `pesticide.psis_code`, `diseaseUseSeq` → `registration.psis_use_seq`, `cropCd` → `crop.ext_code`, `diseaseWeedName` → `pest.name`, `indictSymbl` → `moa.label_kr`, `pestiKorName` → `item_name`, `pestiBrandName` → `name`, `engName` → `ingredient_en`, `useName` → `use_name`.
- **멱등:** `pesticide(psis_code)`, `registration(pesticide_id, psis_use_seq)` 기준 upsert, 한 트랜잭션, 실패 시 롤백(기존 데이터 유지). 성공 시 `loaded_at`을 갱신한다.

### PSIS 문자열 파서 (순수 함수 + 테스트, 팀장 작업)
- `parse_phi(useSuittime) -> int | None`: 숫자 하나만 있으면 그 일수 (「수확 14일 전까지」, 「수확 14일전」 → 14). 「당일」이 들어 있으면 0. **숫자가 둘 이상(서로 다른 값)이거나 숫자가 없으면 `None`.**
- `parse_max_uses(useNum) -> int | None`: 「N회」의 N (「5회 이내」 → 5). 숫자가 없거나 서로 다른 숫자가 둘 이상이면 `None`.
- 파서가 `None`을 돌려줘도 원문은 `*_raw` 컬럼에 항상 저장한다.
- 파싱 실패율은 S1 샘플 조사에서 측정한다 (judge_rules §10-3, §10-6).

## 9. 공통 규칙

- **에러 형식:** `{"error": {"code", "message", "details?"}}`. 프론트는 `code`로 분기한다. FastAPI 기본 422도 같은 형식으로 감싼다.

  | code | HTTP |
  |---|---|
  | `UNAUTHORIZED` | 401 |
  | `NOT_FOUND` | 404 |
  | `VALIDATION_ERROR` | 422 |
  | `PLANTED_AT_REQUIRED` | 422 |
  | `PARCEL_ALREADY_USED` | 409 |
  | `UPSTREAM_ERROR` | 502 |

- **설정:** `pydantic-settings`로 환경변수를 읽는다 (`DATABASE_URL`, `JWT_SECRET`, `KAKAO_*`, `JUSO_CONFM_KEY`, `FARMMAP_API_KEY`, `PSIS_API_KEY`, `NCPMS_API_KEY`, `CORS_ORIGINS`). 누락되면 기동에 실패한다. 토큰과 키는 로그에 남기지 않는다.
- **인증:** PyJWT. `core`의 `current_user`와 `get_owned_zone(zone_id)` 의존성이 소유자 검사를 **한 곳에서** 처리한다.
- **DB:** 요청당 세션 1개. 첫 마이그레이션에서 `CREATE EXTENSION postgis`.
- **날짜:** "오늘"은 항상 **KST**(`today_kst()`)다. 서버 시간대에 따라 ③ 횟수와 기본 살포일이 하루 어긋나는 것을 막는다.
- **CORS:** 프론트가 분리되어 있으므로 `CORSMiddleware`를 쓰고 `CORS_ORIGINS`로 허용 도메인을 지정한다.
- **계약 파일:** `openapi.json`을 저장소에 커밋한다 (`python -m app.export_openapi`로 생성). 이 파일을 바꾸는 PR은 프론트 승인이 필요하다.
- **린트:** `ruff` (포맷 + 린트).
- **테스트:**
  - `judge/rules.py`: DB 없이 표 기반 pytest. 케이스 원본은 `farmguardian_judge_rules.md` §9.
  - 연동·PSIS 파서·팜맵 파서: §8의 fixture(명세서 예시 응답 포함)와 표 기반 pytest.
  - API: `TestClient` + **실제 PostGIS 테스트 DB** (`ST_*` 때문에 SQLite 불가). 테스트마다 트랜잭션 롤백. 구역 분할은 파티션 검증, 이력 복사, 필지 중복(409) 케이스를 여기서 다룬다.
  - 문구 검사: `message`·`notices` 템플릿에 금지어(`추천 예측 예상 가능성 위험 확률 안전 문제없`)가 없는지 스캔.
  - S4에 e2e 스모크 1개.

## 10. 미결 사항

판정 규칙의 미결은 `farmguardian_judge_rules.md` §10이 원본이다. 여기에는 구조·일정에 영향을 주는 것만 둔다.

**닫힌 것** (2026-10-04): ② 수확 가능일 표시, ③ 품목명 기준, ④ 임계값(3회 중 2회)과 `moa` NULL 기본안, 편중도 작기 창, 대안 규칙, 문구, PSIS 데이터 형태 대부분, 구역 분할(필지 단위, 생성 시 + 사후, 이력 복사).

**남은 것**
1. **성분 단위 합산 여부.** 틀리면 "가능"이 잘못 나오는 위험한 방향이다. **출시 전 확인.**
2. **PSIS 샘플 조사 (S1 월요일).** 스키마 동결 전에 끝낸다. 항목은 judge_rules §10-3.
3. **다작용점 약제의 ④ 제외 여부.** 농학 전문가 확인.
4. **면책 문구.** 제품·법무 확인.
5. **별표 8 매핑표** (한글 작용기작 기호 → FRAC·IRAC) 담당과 전달 시점.
6. **프론트와 합의:** 「상태 요약」의 의미 (`last_spray` + `last_judgment`로 가정, 오래된 판정이 현재 상태처럼 보이는 위험), 편중도 화면(작기 비율), 대안·약제 목록 묶음 방식, 카카오 Redirect URI, 필지 선택·분할 화면 (`matches_query`·`used_by_zone_id` 표시, 사후 분할 때 이력이 복사된다는 안내).
7. **외부 확인:** 도로명주소·팜맵·PSIS·NCPMS 키, 지원 작물 목록과 다년생 여부. 팜맵 최신성은 명세서 예시의 영상촬영년도가 2016이라 실제 응답의 `vdptYr`로 확인한다. 공공데이터포털 팜맵 키의 일일 호출 한도는 명세서에 없다.
8. **NCPMS 병해충과 PSIS 병해충명 매칭** (도감 사진·증상 부위 연결). 이름 표기가 달라 매칭 규칙이 필요하다.
9. **서버 고정 출력 IP.** 팜맵 오류코드 32(등록되지 않은 IP)가 있다. 필요하면 배포 환경에서 고정 IP를 마련해 키 신청 때 등록한다.
10. **팜맵 면적·경계 안내 문구.** 지적도가 아니며 법적 효력이 없다는 점을 화면에 어떻게 표시할지 (면책 문구와 함께 정한다).

## 11. 착수 전 준비물

- 프로젝트가 **git 저장소가 아니다.** 2명 협업 전에 `git init`과 원격 저장소를 만든다.
- `docker-compose`로 `postgis/postgis` 개발 DB (팀원 S1 첫 작업).
- 1일차 신청: 도로명주소 API 승인키, **팜맵 조회 API**(공공데이터포털 활용신청, 서버 고정 IP 등록이 필요한지 확인), 카카오 개발자 앱 등록, **PSIS·NCPMS API 키** (PSIS는 `psis.rda.go.kr`에서 발급. 샘플 조사에 필요하며 발급 대기시간이 있다).

## 12. 다른 문서에 반영된 변경점

- `farmguardian_flow_spec.md`: §4 면적 "신발끈 공식" → `ST_Area`, §3에 `farmguardian_judge_rules.md` 우선 안내, Setup·Edit에 구역 분할, §2에 팜맵 PNU 조회가 중첩 필지를 돌려준다는 설명.
- `farmguardian_team_plan.md`: 팀원 S2 "신발끈 면적 함수" → 필지 저장·조회 쿼리(`ST_*`), PSIS 파서·팜맵 GML 파서(S1), 구역 분할 API(S2 생성 시, S3 사후), 팀장 S3 `copy_history`, 1일차 신청에 팜맵·카카오·PSIS·NCPMS 추가, `git init`·docker-compose를 S1에 추가, 위험표·미확정 갱신, **담당 재배분** (팜맵·구역 만들기 = 팀원, 나머지 = 팀장).
