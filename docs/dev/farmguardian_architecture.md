# 팜가디언 백엔드 아키텍처 (개발 뼈대)

- 작성일: 2026-10-04, **개정 2026-10-11 (PRD 반영: 밭·구역 도형 분할, 정식일 선택, 누락 확인, 날씨, 병해충 이름 검색·매개충, 기록 재시도·중복 확인, 수동 구역·이력 수정·사후 분할 삭제)**
- 기준 문서: `PRD.md` (제품 요구), `farmguardian_flow_spec.md` (흐름 · 입출력), `farmguardian_judge_rules.md` (**판정 규칙 · 타입 · 문구 · 테스트 케이스**), `farmguardian_team_plan.md` (분담 · 일정), 농촌진흥청 `농약등록정보 Open API 기술명세서 (ver 1.0)`, 농림수산식품교육문화정보원 `팜맵 조회 Open API 활용가이드`
- PRD와 다르게 정한 항목은 `farmguardian_prd_feedback.md`에 PRD 수정 제안으로 모았다.
- 상태: 설계 승인됨 (2026-10-11 PRD 반영안 승인).
- 이 문서는 **S1 월~화 산출물(스키마, `judge()` 타입, API 계약)의 기준**이다. 판정 규칙의 세부는 `farmguardian_judge_rules.md`가 우선한다.

## 1. 목적과 범위

농가가 구역·병해충·약제를 고르면 4체크(①등록 ②시기 ③횟수 ④작용기작)로 사용 가능 여부(가능/주의/불가/확인 필요)를 알려주는 앱의 **백엔드**.

범위 안: 인증(아이디·비밀번호 가입·로그인, 첫 사용 온보딩 상태, 회원 탈퇴 포함), 밭(팜맵 필지)과 구역(밭 도형을 개수·방향·비율로 분할), 병해충 후보·도감 목록·이름 검색·매개충, 약제 목록, 판정, 살포 기록·조회·취소, 구역 위치의 강수 예보, 외부 데이터 연동·적재, 시연용 데모 데이터.

범위 밖: 프론트엔드 설계, 배포 상세, 구역 재분할·병합(P1. 지금은 밭을 지우고 다시 만든다), 선 긋기·경계 드래그 분할(P1), 주소 없는 수동 구역, 이력 수정(취소 후 다시 입력), 포장지 OCR·희석 계산·논문 실측값(P1), 날씨 기반 살포 판정, 알림.

## 2. 확정 결정

| 항목 | 결정 |
|---|---|
| DB | PostgreSQL + **PostGIS**. 필지·밭·구역 도형은 `geometry(MultiPolygon, 5179)` |
| 면적 | `ST_Area(zone.geom)` (SRID 5179가 미터 평면이므로 결과가 ㎡). **팜맵 기준 참고값**이며 지적 면적과 다를 수 있다 |
| 로그인 | **아이디·비밀번호 가입과 로그인.** 가입 때 팜맵 필지를 함께 등록해 첫 밭을 만든다. 카카오 로그인은 쓰지 않는다. 해커톤 시연용이라 보안은 최소로 한다 (2026-10-28) |
| 세션 | 토큰 없음. 가입·로그인 응답의 `id`를 프론트가 저장해 모든 요청에 `X-User-Id` 헤더로 보낸다. 비밀번호는 `hashlib.scrypt`로 해시해 저장한다 |
| 프레임워크 | FastAPI, **동기** 엔드포인트 |
| DB 접근 | SQLAlchemy 2.0 (동기) + GeoAlchemy2 + Alembic |
| 코드 구조 | **DDD: 바운디드 컨텍스트 5개(identity·farm·catalog·judgment·spraying) × 4층(domain·application·infrastructure·presentation)** (§4) |
| 판정 모델 | Pydantic 모델 하나를 `judge()` 입출력과 API 응답에 공통 사용 |
| 상태 코드 | `OK / CAUTION / BLOCKED / NEEDS_CHECK` (가능 / 주의 / 불가 / 확인 필요). PRD 표기(GREEN·AMBER·RED·UNKNOWN)는 쓰지 않는다. 색이 아니라 의미 이름이라 화면 색이 바뀌어도 계약이 그대로다 |
| 지도 | 사용 안 함. 폴리곤 좌표를 내려주고 프론트가 SVG로 렌더링. 분할 미리보기도 같은 방식 |
| 밭과 구역 | **밭(`field`) = 사용자가 고른 팜맵 필지(`fmapInnb`)들의 합친 경계. 구역(`zone`) = 밭 도형을 자른 조각.** 한 필지에 여러 작물을 심는 경우를 표현하려고 필지 묶음 대신 도형 분할을 택했다 |
| 구역 분할 | 백엔드가 방향·비율로 밭 도형을 잘라 미리보기를 주고, 같은 입력으로 구역을 만든다. 균등 분할 = 비율이 모두 1. **비율 입력(예 6:4)이 PRD의 「경계 드래그 수정」을 대신한다** (프론트가 균등 분할 화면까지만 감당). 선 긋기·드래그는 P1 |
| 정식일 | **선택 항목** (`zone.planted_at` NULL 허용). 없으면 ③ = 확인 필요 |
| 작기 | ③ 창 = 정식일 이후. 지원 작물(**감자·배추·토마토**)이 모두 일년생이라 다년생 분기 없음. 작물을 바꾸면 정식일을 새로 받거나 비운다. **작기 테이블 없음** |
| 이력 확인 | `zone.history_confirmed` (「누락 없음」). 확인 전이면 이력 건수와 무관하게 ③④ = 확인 필요. 정식일이 바뀌면 풀린다 |
| ② 시기 | 수확 예정일 입력 없음. "오늘 살포하면 N월 N일부터 수확 가능"을 계산해 표시 (`BLOCKED` 없음) |
| ③ 집계 단위 | **품목명(`item_name`) 기준 합산.** 성분 단위는 미확인 (judge_rules §10-1) |
| 편중도 | 작기 전체 비율 (④ 판정의 최근 3회 창과 별개). 정식일이 없으면 전체 이력 |
| 약제·병해충 원천 | **엑셀 7개**(`docs/*.xlsx`, 팀이 PSIS·NCPMS 자료를 정리한 것, 기준일 2026-10-05)를 JSON으로 바꿔 DB에 적재한다. PSIS·NCPMS API는 호출하지 않는다 (2026-10-28 결정, §8). `data_asof` = 엑셀 기준일 |
| 팜맵 필지 | 팜맵 조회 Open API(공공데이터포털). 밭의 필지 단위는 **팜맵 필지(`fmapInnb`)** 이지 지번이 아니다. 한 지번이 여러 필지일 수 있고 PNU 조회는 이웃 지번과 겹치는 필지까지 돌려준다. 법적 효력 없는 참고 자료 |
| 날씨 | 기상청 단기예보. 구역 중심점의 격자 좌표로 **요청 시 조회, 저장·캐시 없음.** 판정과 별도 엔드포인트라 날씨가 실패해도 판정은 동작한다 |
| 살포 기록 | 클라이언트가 보내는 `request_id`로 **재시도를 한 번만 반영.** 같은 구역·상표·날짜 기록이 있으면 409로 묻고 `allow_duplicate`로 별도 저장. 취소 = 삭제 |
| 화면 구조 | 프론트 탭 4개: **홈**(내 밭·구역 상태), **병해충**(구역 → 병해충 → 약제 → 판정 → 기록), **조회수정**(이력·구역·밭), **프로필**(출처·면책 안내, 로그아웃, 회원 탈퇴). 첫 사용은 가입(필지 등록으로 첫 밭 생성) → 구역 나누기 → 과거 살포 입력·「누락 없음」 확인을 마쳐야 탭을 쓸 수 있다 (2026-10-11) |
| 온보딩 상태 | `users.onboarded_at`. 프론트가 온보딩 끝에 `POST /me/onboarding`으로 기록한다. 구역의 「누락 없음」은 정식일이 바뀌면 풀리므로 온보딩 완료 여부로 쓰지 않는다 |
| 회원 탈퇴 | `DELETE /me`: 사용자와 밭·구역·기록·판정을 모두 지운다 |

## 3. 시스템 구성

```
프론트(SPA) ── HTTPS/JSON, X-User-Id ──▶ FastAPI (app/)
                                            │
     ┌──────────┬──────────┬──────────┬──────┴─────┬──────────┐
  identity/    farm/     catalog/   judgment/   spraying/
                 │           ▲
    farm/infrastructure/     │
        integrations         │
                 │           │
  도로명주소 · 팜맵 · 기상청 (요청 시 호출)        PostgreSQL + PostGIS
                                                                   ▲
              엑셀 7개 → JSON ── catalog 적재 (수동 실행) ──┘
```

## 4. 코드 구조

DDD로 나눈다. **바운디드 컨텍스트 5개**를 최상위 폴더로 두고, 각 컨텍스트 안을 `domain / application / infrastructure / presentation` 4층으로 나눈다.

```
app/
  core/                       설정, DB 세션, 에러 형식, 공통 의존성, today_kst()
  identity/                   사용자 가입·로그인, users                              (팀장)
  farm/                       밭(field)·구역(zone) 애그리거트                          (밭·분할·연동 = 팀원, 구역 = 팀장)
    domain/                   밭·구역 엔티티, split.py(분할 위치 계산, 순수)
    application/              field_service.py (팀원), zone_service.py (팀장)
    infrastructure/           models.py, 리포지토리
      integrations/           juso.py, pnu.py, farmmap.py (GML 파서), kma.py (격자 변환·예보)
    presentation/             router.py, schemas.py
  catalog/                    참고 데이터: 작물·병해충·약제·등록·작용기작               (팀장)
    domain/                   pest, pesticide, registration, moa
    application/              병해충 후보·도감 목록·이름 검색, 약제 목록
    infrastructure/           models.py
      ingest/                 xlsx_to_json.py, load.py, data/*.json
    presentation/             router.py, schemas.py
  judgment/                   4체크 판정                                               (팀장)
    domain/                   schemas.py, rules.py (순수)
    application/              service.py (판정 실행·저장, rotation_summary)
    presentation/             router.py
  spraying/                   살포 기록(spray_log) 기록·조회·취소                      (팀장)
    domain/ application/ infrastructure/ presentation/
  seed_demo.py                시연용 데모 계정·밭·구역·이력                             (팀장)
tests/
openapi.json
```

층별 규칙:
- `domain`: 엔티티·값 객체·순수 규칙. DB·HTTP·FastAPI를 임포트하지 않는다. `judgment/domain/schemas.py`, `judgment/domain/rules.py`, `farm/domain/split.py`가 이 규칙의 핵심이다.
- `application`: 유스케이스(서비스 함수). `domain`과 같은 컨텍스트의 `infrastructure`를 쓴다. 트랜잭션 경계는 여기다.
- `infrastructure`: SQLAlchemy 모델·리포지토리, 외부 API 클라이언트, 적재 스크립트.
- `presentation`: FastAPI 라우터와 요청·응답 스키마. `application`만 호출한다.
- 의존 방향은 `presentation → application → domain`, `application → infrastructure`다. `domain`은 아무것도 가리키지 않는다.

컨텍스트 사이 규칙:
- 다른 컨텍스트는 상대의 **`application` 서비스 함수만** 임포트한다. 남의 `domain` 엔티티나 `infrastructure` 모델을 직접 쓰지 않는다. 경계를 넘는 호출:
  - 구역 상세의 편중도: `farm`이 `judgment.application.service.rotation_summary`를 호출
  - 가입: `identity`가 `farm.application.field_service`로 첫 밭을 만든다
  - 판정 입력: `judgment`가 `farm`(구역·정식일), `catalog`(약제·등록), `spraying`(이력)의 `application` 서비스로 값을 받아 `rules.py`에 넘긴다. `judgment`에는 `infrastructure`가 없다
  - 날씨: `farm.infrastructure.integrations.kma`가 같은 컨텍스트의 `zone_service.centroid_wgs84(zone_id)`로 위치를 받는다
- `farm` 안에서 밭(팀원)과 구역(팀장)은 서비스 파일로 담당을 나눈다. 구역 생성은 `field_service`가 `zone_service.create_many(field_id, user_id, parts)`를 호출하고, 밭 목록의 구역 요약은 `zone_service.summaries(field_ids)`다. 이 함수 세 개(`create_many`, `summaries`, `centroid_wgs84`)는 팀장이 제공한다.
- 폴더가 담당자 경계다. 경계를 넘는 수정은 상대 리뷰를 받는다.

## 5. DB 스키마

엑셀·팜맵 필드와의 대응을 괄호로 표시한다. **PSIS·NCPMS 원본 코드는 엑셀에 없다 (§5 끝의 「엑셀 적재에 따른 조정」 참조).**

```
users(id, username, password_hash, onboarded_at NULL, created_at)
                                                           UNIQUE(username). onboarded_at = 첫 사용 온보딩 완료 시각
crop(id, name, ext_code)                                   ext_code = cropCd. UNIQUE(ext_code)
pest(id, name, kind NULL, ncpms_code NULL)                 name = diseaseWeedName. UNIQUE(name). kind = '병' | '해충' (엑셀 `2_병해충_도감`의 구분)
pest_info(pest_id, crop_id, photo_url NULL, description NULL,
          occurrence NULL, source, loaded_at)              PK(pest_id, crop_id). 엑셀 `2_병해충_도감`(작물별)의
                                                           사진·설명·발생시기. source·loaded_at = 출처·기준 시점
pest_symptom(pest_id, crop_id, part)                       PK 3개. 증상 부위 → 후보
pest_vector(virus_pest_id, vector_pest_id, source)         PK(virus_pest_id, vector_pest_id). 바이러스 → 매개충.
                                                           엑셀 `7_바이러스_매개충`, 근거(출처) 필수
moa(id, label_kr, system NULL, code NULL)                  label_kr = indictSymbl (예: 라3). UNIQUE(label_kr)
                                                           system/code = FRAC·IRAC (별표 8 매핑으로 채움)
pesticide(id, psis_code, name, item_name, company,
          ingredient_en, use_name, moa_id NULL)            psis_code = pestiCode. UNIQUE(psis_code)
                                                           name = pestiBrandName, item_name = pestiKorName,
                                                           ingredient_en = engName, use_name = useName
registration(id, crop_id, pest_id, pesticide_id, psis_use_seq,
             phi_days NULL, max_uses NULL,
             use_suittime_raw, use_num_raw, dilut_raw, use_method, usage_type,
             loaded_at)                                    psis_use_seq = diseaseUseSeq
                                                           UNIQUE(pesticide_id, psis_use_seq)
                                                           CHECK phi_days >= 0, max_uses > 0
field(id, user_id, name, geom geometry(MultiPolygon, 5179), created_at)
                                                           geom = 고른 필지 도형의 합집합 (ST_Multi(ST_Union))
field_parcel(id, field_id, user_id, farmmap_id, pnu, lnm, land_use, vdpt_yr,
             geom geometry(MultiPolygon, 5179), fetched_at) UNIQUE(user_id, farmmap_id)
                                                           farmmap_id = fmapInnb, pnu = pnuLnmCd,
                                                           lnm = 지번 표기 (예: 161-7 전),
                                                           land_use = intprNm (논·밭·과수·시설),
                                                           vdpt_yr = vdptYr (영상촬영년도)
                                                           user_id는 field.user_id의 복사본 (서비스가 일치시킨다)
zone(id, field_id, user_id, name, crop_id, planted_at NULL,
     history_confirmed bool default false,
     geom geometry(MultiPolygon, 5179))                    geom = 밭을 자른 조각. user_id는 field.user_id의 복사본
spray_log(id, zone_id, pesticide_id, sprayed_on, source, request_id uuid)
                                                           source = 'manual' | 'app'. UNIQUE(request_id)
judgment(id, zone_id, pest_id NULL, pesticide_id, verdict,
         result jsonb, created_at)
```

외래키 `field_parcel.field_id`, `zone.field_id`, `spray_log.zone_id`, `judgment.zone_id`는 `ON DELETE CASCADE`다. 밭 삭제가 구역·기록·판정을 함께 지운다. `field.user_id`, `field_parcel.user_id`, `zone.user_id`도 `users`에 `ON DELETE CASCADE`라서 회원 탈퇴가 사용자 데이터를 모두 지운다.

인덱스: `spray_log(zone_id, sprayed_on DESC)`, `judgment(zone_id, created_at DESC)`, `registration(crop_id, pesticide_id)`, `registration(crop_id, pest_id)`, `pesticide(item_name)`, `field_parcel(field_id)`, `zone(field_id)`. 공간 검색이 없으므로 공간 인덱스는 만들지 않는다.

규칙이 스키마에 붙는 방식 (세부 판정은 judge_rules):
- ①등록 = `registration` 행 존재. ②③ 값 = `phi_days`, `max_uses`. 병해충 미지목이면 ①은 확인 필요이고 ②③은 고른 상표의 작물 행 전체에서 가장 엄격한 값. **PSIS가 준 문자열을 못 읽은 행은 값이 NULL**이고 원문 컬럼에 남아 있어 `NEEDS_CHECK`와 근거 표시에 쓴다.
- ③ 횟수 = `spray_log`를 `pesticide.item_name`으로 조인해 **같은 품목명**이고 `sprayed_on >= planted_at`인 건수. `planted_at`이 NULL이면 확인 필요. 작물을 바꾸면 `planted_at`을 새 값이나 NULL로 바꾸므로 다시 센다. **작기 테이블은 두지 않는다.**
- ④ = 구역 이력을 최근순으로 보고 고른 약제와 `moa.label_kr`이 같은 기록이 **연속**된 건수를 계열별 허용 횟수(`6_반복규칙`)와 비교 (judge_rules §4).
- 「누락 없음」 = `zone.history_confirmed`. `planted_at` 값이 바뀌면 `false`로 되돌린다 (같은 요청에서 `history_confirmed`를 명시하면 그 값).
- 구역 면적 = `ST_Area(zone.geom)`, 밭 면적 = `ST_Area(field.geom)`.
- 필지 도형은 밭을 만들 때 팜맵에서 **1회** 받아 저장한다 (스펙 §1). 밭 도형은 그 합집합이고 구역 도형은 밭을 자른 것이라 다시 받지 않는다.
- **필지는 사용자당 한 밭에만 속한다** (`UNIQUE(user_id, farmmap_id)`).
- 팜맵은 지적도가 아니라 실제 경작 구획을 판독한 지도이고 법적 효력이 없다. 면적·경계는 참고값이다.
- 판정은 호출마다 `judgment`에 저장한다. `result`에 근거 원문·기준일 스냅샷이 들어 있어 데이터가 바뀌어도 당시 화면을 재현할 수 있다.
- `data_asof`는 엑셀 기준일(2026-10-05, `4_약사용규칙` 안내 시트의 수정본 날짜)이다. 화면에서는 "데이터 조회일"로 표기한다.
- 병해충은 코드 없이 **이름 문자열**로 연결한다. 엑셀 `2_병해충_도감`의 이름(NCPMS 도감 이름)이 기준이고, `3_`·`4_`의 병해충 이름과 같아야 한다. 도감에 없는 병해충(PSIS에만 있는 13개)은 사진·증상이 「없음」이다.
- 매개충(`pest_vector`)의 두 병해충은 모두 `pest` 행이어야 한다. 적재 때 이름이 `pest`에 없으면 그 줄을 건너뛰고 로그를 남긴다.
- **엑셀 적재에 따른 스키마 조정 (초안, 스키마를 확정할 때 반영한다):**
  - 없어지는 것: `crop.ext_code`, `pesticide.psis_code`, `registration.psis_use_seq`, `pest.ncpms_code` (엑셀에 PSIS·NCPMS 코드가 없다). `registration`의 구분 키는 `(crop, pest, pesticide, 사용 방법, 희석배수)`다.
  - 생기는 것: `registration.use_method`(사용 방법), `dilution`(희석배수 원문), `usage_type`(`성공`·`심을 때`·`제한 없음`·`확인 필요`), `note`(비고), `pesticide.company`와 `first_reg_date`(`3_`에서), `pest.scientific_name`, 발생 시기 테이블(`1_`), 사진 테이블(`2_`의 사진 시트), `moa`의 국제 코드(`system`·`code`는 `5_약계열`의 「FRAC 24」 같은 값을 나눠 채운다).
  - ④ 반복 규칙(`6_반복규칙`)을 어떻게 저장·적용할지는 판정 규칙 개정과 함께 정한다 (미결).

## 6. `judge()` 타입

전체 정의, 규칙, 문구, 테스트 케이스는 **`farmguardian_judge_rules.md`** 를 따른다. 여기에는 구조의 요약만 둔다.

```python
Verdict: OK, CAUTION, BLOCKED, NEEDS_CHECK       # 가능 / 주의 / 불가 / 확인 필요
JudgeInput:  today, planted_at | None, history_confirmed, pest_id | None,
             pesticide_id, item_name, moa | None,
             registrations (고른 상표의 이 작물 행 전부), history (구역 전체 이력), psis_asof
CheckResult: key (registration|timing|count|moa), status, message, facts, evidence (항상 있음)
JudgeResult: pesticide_id, moa, verdict, checks (항상 4개), notices: list[str], data_asof (항상 있음)

judge(inp) -> JudgeResult
rotation_summary(history, planted_at) -> RotationSummary
pick_alternatives(selected, others) -> list[JudgeResult]       # 필터만. 이름 채움·정렬은 서비스
```

설계 근거:
- **체크 4개를 항상 반환**한다. 프론트가 4체크 목록을 고정 렌더링한다. 체크 상태는 `Verdict`를 재사용하고 최종 `verdict`는 최고 우선순위 하나.
- **`message`(한글 사유 문장)와 `notices`는 백엔드가 생성**한다. "예측·추천 표현 금지" 규칙을 한 곳에서 테스트하기 위해서다. 프론트는 색과 아이콘만 담당한다.
- **`facts` 키는 체크별로 문서에 고정**한다. dict라 타입은 약하지만 1달 일정에 맞춘 선택이다. ③의 `remaining`·`remaining_after`가 PRD의 「현재 남은 횟수 / 이번 사용 후 남을 횟수」다.
- **근거는 체크마다 항상 있다** (PRD §6-3-6). 원문이 없으면 「없음」.
- **대안은 `judge()` 밖에서 만든다.** 서비스가 같은 작물×병해충의 다른 약제들도 `judge()`로 돌려 `pick_alternatives`에 넘긴다.
- 「농업기술센터 문의」는 API 응답 필드(`show_extension_office`)이며 병해충을 지목했고 불가·주의에 대안이 0건일 때만 true다.

## 7. API

요청·응답·오류의 상세 계약은 **`farmguardian_api_spec.md`**가 기준이다. 아래 표와 동작 규칙은 설계 근거이고, 어긋나면 api_spec을 따른다.

모든 엔드포인트는 `X-User-Id` 헤더가 필요하다 (`/auth/*`, `GET /addresses/search`, `GET /parcels`만 예외). 헤더가 없거나 없는 사용자이면 401. `/fields/{id}/*`, `/zones/{id}/*`는 소유자 검사를 하고 남의 것은 **404**를 돌려준다.

| 메서드 경로 | 용도 | 요청 → 응답 핵심 | 컨텍스트 |
|---|---|---|---|
| `POST /auth/signup` | 가입 + 첫 밭 생성 | `{username, password, field_name, parcel_farmmap_ids[]}` → 201 `{id, username, field: Field}` | identity |
| `POST /auth/login` | 로그인 | `{username, password}` → `{id, username}` (틀리면 401) | identity |
| `GET /me` | 내 정보 (온보딩 여부) | → `{id, username, onboarded}` | identity |
| `POST /me/onboarding` | 온보딩 완료 기록 | → `{id, onboarded: true}` | identity |
| `DELETE /me` | 회원 탈퇴 | → 204 | identity |
| `GET /crops` | 작물 목록 | → `[{id, name}]` | catalog |
| `GET /addresses/search` | 주소 검색 (인증 없음. 가입 전에 쓴다) | `?keyword&page` → `{total, items: [{road_addr, jibun_addr, pnu}]}` | farm |
| `GET /parcels` | 주소와 겹치는 팜맵 필지 조회 (인증 없음. 로그인 전이면 `used_by_field_id`는 null) | `?pnu` → `[Parcel]` (선택 화면용 폴리곤, 이웃 지번 필지 포함) | farm |
| `POST /fields` | 밭 생성 | `{name, parcel_farmmap_ids[]}` → `Field` | farm |
| `GET /fields` | 내 밭 (밭별 구역 요약) | → `[Field]` | farm |
| `DELETE /fields/{id}` | 밭 삭제 (구역·기록·판정 포함) | → 204 | farm |
| `POST /fields/{id}/split-preview` | 분할 미리보기 (저장 안 함) | `{direction, ratios}` → `[SplitPiece]` | farm |
| `POST /fields/{id}/zones` | 구역 생성 | `{direction, ratios, zones: [ZoneSpec]}` → `[Zone]` | farm |
| `GET /zones/{id}` | 구역 상세 | → `Zone` + `rotation` + `recent_judgments` | farm |
| `PATCH /zones/{id}` | 구역 수정 | `{name?, crop_id?, planted_at?, history_confirmed?}` → `Zone` | farm |
| `GET /zones/{id}/weather` | 구역 위치 강수 예보 | → `Weather` | farm |
| `GET /crops/{id}/symptom-parts` | 증상 부위 목록 | → `[part]` | catalog |
| `GET /pests/candidates` | 증상 부위로 병해충 후보 | `?crop_id&part` → `[PestCard]` | catalog |
| `GET /pests` | 도감 목록·이름 검색 | `?crop_id&q?` → `[PestCard]` | catalog |
| `GET /pesticides` | 등록 약제 목록 | `?crop_id&pest_id?` → `[{id, name, item_name, moa}]` | catalog |
| `POST /zones/{id}/judgments` | 판정 | `{pesticide_id, pest_id?}` → `JudgeResponse` (저장함) | judgment |
| `POST /zones/{id}/sprays` | 기록 (「살포 기록 저장」, 과거 이력) | `{pesticide_id, sprayed_on?, source, request_id, allow_duplicate?}` → `Spray` | spraying |
| `GET /zones/{id}/sprays` | 이력 | `?limit&offset` → `{total, items: [Spray]}` | spraying |
| `DELETE /zones/{id}/sprays/{sid}` | 기록 취소 | - | spraying |

공통 응답 모양:

```
Parcel        {farmmap_id, pnu, lnm, land_use, vdpt_yr, area_m2, geometry,
               matches_query, used_by_field_id}
              geometry = GeoJSON MultiPolygon, EPSG:5179 미터, y축 위쪽, 소수 1자리 (아래 모든 geometry 동일)
              matches_query (조회한 지번과 같은 필지인지), used_by_field_id (이 사용자의 다른 밭이
              이미 쓰는 필지면 그 밭 id, 아니면 null)
Field         {id, name, area_m2, geometry, bbox: [minx, miny, maxx, maxy], zones: [ZoneSummary]}
              zones가 비어 있으면 아직 나누지 않은 밭
Zone          {id, field_id, name, crop, planted_at | null, history_confirmed, area_m2, geometry, bbox}
ZoneSummary   {id, name, crop, planted_at | null, history_confirmed, area_m2, geometry,
               last_spray | null, last_judgment | null}
ZoneSpec      {name, crop_id, planted_at?}
SplitPiece    {geometry, area_m2}             순서 = 방향의 시작 쪽부터, ratios 순서와 같다
Spray         {id, pesticide: {id, name, item_name, moa}, sprayed_on, source}
Alternative   {id, name, item_name, moa}          Pesticide와 같은 모양
JudgeResponse {judgment_id, result: JudgeResult, alternatives: [Alternative],
               show_extension_office: bool}
rotation      {window_start | null, total, items: [{moa | null, count}]}
              예: {2026-05-01, 7, [{가1, 4}, {나2, 2}, {null, 1}]}. 비율은 프론트가 count/total.
              window_start가 null이면 정식일이 없어 전체 기록 기준
Weather       {issued_at, items: [{at, pty, pcp, pop}]}
              issued_at = 예보 발표 시각(KST), at = 예보 시각, 앞으로 24시간.
              pty = 강수형태 코드, pcp = 1시간 강수량 원문 문자열 (예 "강수없음", "1.0mm"), pop = 강수확률(%)
PestCard      {id, name, kind, photo_url, description, occurrence, source, vectors: [{id, name, source}]}
              photo_url~source는 이 작물의 pest_info (없으면 null → 화면에 「없음」).
              vectors는 바이러스의 매개충 (자료가 없으면 빈 목록 → 화면에 「연결 자료 없음」)
```

동작 규칙:
- **가입:** 한 트랜잭션에서 사용자를 만들고, 밭 생성(`POST /fields`와 같은 규칙: 필지 1~20개, 도형 병렬 조회, 합집합 저장)까지 한다. 필지 조회가 실패하면 502 `UPSTREAM_ERROR`이고 사용자도 만들어지지 않는다. 아이디 중복은 409 `USERNAME_TAKEN`. 다른 회원이 같은 필지를 써도 막지 않는다 (`PARCEL_ALREADY_USED`는 같은 사용자의 다른 밭이 쓰는 필지에만). 가입 뒤 밭 추가·삭제는 `POST /fields`, `DELETE /fields/{id}`.
- **온보딩:** 프론트는 로그인 직후 `GET /me`의 `onboarded`가 false면 온보딩(구역 나누기 → 구역별 과거 살포 입력·「누락 없음」)으로 보낸다. 중간에 나갔다 오면 `GET /fields`(구역 유무, 구역별 `history_confirmed`)로 어디까지 했는지 보고 이어서 한다. 끝나면 `POST /me/onboarding`. 서버는 구역이 1개 이상이고 모든 구역이 「누락 없음」일 때만 기록하고, 아니면 422 `ONBOARDING_INCOMPLETE`. 이미 완료면 그대로 200 (멱등). 온보딩 뒤에 밭을 더 만들 때는 막지 않는다.
- **회원 탈퇴:** DB 삭제(`users` CASCADE) 후 204. 탈퇴 뒤 남은 `X-User-Id`는 사용자가 없으므로 401.
- **작물 변경 = 새 작기.** `PATCH`에서 `crop_id`가 바뀌면 `planted_at`은 요청 값, 없으면 NULL이 된다. NULL이면 ③은 정식일을 넣을 때까지 확인 필요다.
- **`planted_at` 값이 바뀌면 `history_confirmed`는 false**가 된다 (같은 요청에서 명시하면 그 값). 기록은 지우지 않는다. 이번 작기에 드는 기록은 프론트가 `sprayed_on >= planted_at`으로 구분해 보여준다 (PRD §4-2-2).
- **폴리곤 좌표:** 프론트가 y축을 뒤집어 SVG로 그린다.
- **살포일:** 미래 날짜는 422로 거부한다 (횟수 창이 꼬이는 것을 막음). 기본값은 `today_kst()`.
- **살포 기록 저장 순서:**
  1. 같은 `request_id`가 **같은 구역**에 이미 있으면 그 기록을 200으로 돌려준다 (재시도. 다시 저장하지 않음). 다른 구역·다른 사용자의 기록이면 그 기록은 보여주지 않고 422 `VALIDATION_ERROR`를 돌려준다.
  2. 같은 구역·`pesticide_id`·`sprayed_on` 기록이 있고 `allow_duplicate`가 true가 아니면 409 `DUPLICATE_SPRAY` + `details.existing`(Spray). 프론트는 「기존 기록 확인 / 실제 별도 살포로 저장 / 돌아가기」를 보여주고, 별도 살포면 같은 `request_id`로 `allow_duplicate: true`를 붙여 다시 보낸다 (409 때는 저장하지 않았으므로 1번에 걸리지 않는다).
  3. 저장하고 201.
- `request_id`는 프론트가 「저장」 동작 하나마다 UUID 하나를 만들고, 네트워크 재시도에는 같은 값을 쓴다.
- **편중도(`rotation`):** 창은 ③과 같은 작기이고 살포 **건수** 기준이다 (④ 판정과 별개).
- **대안:** 병해충을 지목한 판정에만 계산한다. 지목하지 않았고 불가이면 `result.notices`에 안내 한 줄이 붙고 `alternatives`는 빈 목록이다. 정렬은 작용기작 → 품목명 → 상표명.
- **약제 목록:** 같은 품목의 상표가 여럿이라 길 수 있다. 묶어서 보여주는 방법은 프론트와 정한다.
- **병해충 고르기:** `GET /pests`는 `registration`에서 그 작물에 등록된 병해충이고, `q`가 있으면 이름 부분 일치(`ILIKE`)로 거른다. 이름순. **발생시기로 거르지 않는다** (발생시기는 참고 정보). NCPMS 매칭이 없는 병해충도 나온다.
- **매개충:** 사용자가 매개충을 고르면 일반 병해충과 같은 `pest_id`로 약제 목록·판정을 탄다. 매개충 약제를 바이러스 치료로 설명하지 않는다 (프론트 고정 문구, judge_rules §8).
- **날씨:** 판정과 따로 호출한다. 실패하면 502이고 프론트는 「날씨 조회 실패」를 표시한다. 판정에는 영향이 없다.
- `recent_judgments`는 최근 5건.

### 밭과 구역 분할

밭은 팜맵 필지를 합친 경계이고, 구역은 백엔드가 그 경계를 잘라 만든다. 클라이언트가 보낸 도형은 받지 않는다.

**밭 생성 (`POST /fields`)**
- 필지 1개 이상 20개 이하. 떨어진 필지도 한 밭이 될 수 있다 (MultiPolygon).
- 이 사용자의 다른 밭이 이미 쓰는 필지가 있으면 409 `PARCEL_ALREADY_USED` (`details.farmmap_ids`).
- 필지 도형은 **스레드 풀로 병렬 조회**하고 (동시 8개 이하, 평균 600ms × n 직렬 방지) `field_parcel`에 저장한 뒤 합집합을 `field.geom`으로 저장한다. 한 트랜잭션.

**분할 (`POST /fields/{id}/split-preview`, `POST /fields/{id}/zones`)**
- `direction`: 밭의 **긴 변** 기준이다. 긴 변 방향은 최소 회전 사각형(`ST_OrientedEnvelope`)의 긴 변으로 정한다.
  - `crosswise`: 자르는 선이 짧은 변과 나란하다 → 긴 변을 따라 토막이 난다.
  - `lengthwise`: 자르는 선이 긴 변과 나란하다 → 긴 띠가 나란히 생긴다.
- `ratios`: 양의 정수 1~10개. 균등 분할 = `[1, 1, 1]`. 1개면 밭 전체가 구역 하나다.
- 계산: 밭 도형을 긴 변이 x축이 되게 회전한다 → 자르는 위치를 이분 탐색해 누적 면적이 비율과 맞게 찾는다 (허용 오차 전체 면적의 0.1%) → 각 띠를 `ST_Intersection`으로 잘라 원래 각도로 되돌린다. 위치 찾기는 순수 함수 `farm/domain/split.py: cut_positions(rings, ratios) -> list[float]` (반평면 클리핑 + 신발끈 공식, 의존성 추가 없음), 도형 생성은 PostGIS다.
- 오목한 밭은 띠 하나가 조각 여러 개(MultiPolygon)일 수 있다. 그대로 한 구역이다.
- 같은 입력이면 같은 결과다 (결정적). 생성 요청에서 서버가 다시 계산한다.
- `zones` 길이는 `ratios` 길이와 같아야 한다 (아니면 422). `name`·`crop_id` 필수, `planted_at` 선택.
- 이미 구역이 있는 밭에 다시 만들면 409 `FIELD_ALREADY_SPLIT`. **재분할은 P1**이고, 지금은 밭을 지우고 다시 만든다.

**밭 삭제 (`DELETE /fields/{id}`)**
- 구역·기록·판정까지 지운다 (CASCADE). 되돌릴 수 없으므로 프론트가 확인을 받는다.
- 잘못 고른 필지, 다시 나누기는 이걸로 처리한다. 필지 교체 API는 두지 않는다.

## 8. 외부 연동

| 연동 | 파일 | 함수 | 비고 |
|---|---|---|---|
| 도로명주소 | `farm/infrastructure/integrations/juso.py` | `search(keyword, page)` | 승인키(`confmKey`)는 서버 전용. 아래 상세 |
| PNU 조립 | `farm/infrastructure/integrations/pnu.py` | `assemble_pnu(admCd, lnbrMnnm, lnbrSlno, mtYn)` | **순수 함수**, 스펙 §2 공식 |
| 팜맵 | `farm/infrastructure/integrations/farmmap.py` | `parcels_by_pnu(pnu)`, `parcel_by_id(id)`, `parse_farmmap_response(xml)`(순수) | 공공데이터포털 `serviceKey`. 아래 상세 |
| 기상청 | `farm/infrastructure/integrations/kma.py` | `latlon_to_grid(lat, lon)`(순수), `village_forecast(nx, ny, now)`, `parse_forecast(json, now)`(순수) | 공공데이터포털 `serviceKey`. 아래 상세 |
| 약·병해충 데이터 | `catalog/infrastructure/ingest/xlsx_to_json.py`, `load.py` | `python -m app.catalog.infrastructure.ingest.xlsx_to_json`, `…ingest.load` | 외부 API 호출 없음. 엑셀 → JSON → DB. 아래 「데이터 적재」 |

- 공통: `httpx` 동기 클라이언트, 타임아웃 5초, 재시도 없음. 실패는 **502 `UPSTREAM_ERROR`** + `details.source`.
- 테스트: `httpx.MockTransport`로 가짜 응답을 쓴다. **팜맵·도로명주소·기상청 명세서의 예시 응답을 fixture로 저장**하고, 키를 받아 얻은 실제 응답을 더해 재사용한다.

### 도로명주소 검색 (`farm/infrastructure/integrations/juso.py`)

주소기반산업지원서비스 검색 API 가이드(business.juso.go.kr → 주소정보 API 연계 → 검색 API) 기준:
- 호출: `GET https://business.juso.go.kr/addrlink/addrLinkApi.do?confmKey=…&keyword=…&currentPage=1&countPerPage=10&resultType=json`. 서버에서만 호출한다 (JSONP 엔드포인트는 쓰지 않는다).
- 응답: `results.common`(`totalCount`, `currentPage`, `countPerPage`, `errorCode`, `errorMessage`)과 `results.juso[]`. 쓰는 필드는 `roadAddr`, `jibunAddr`, `admCd`(행정구역코드), `mtYn`(0:대지, 1:산), `lnbrMnnm`(지번 본번), `lnbrSlno`(지번 부번)이고, 앞의 두 개는 `GET /addresses/search`의 `road_addr`·`jibun_addr`, 나머지는 `assemble_pnu`의 입력이다. 가이드의 응답표에는 `InbrMnnm`(대문자 I)로 적혀 있지만 샘플 코드는 `lnbrMnnm`이다. 실제 응답으로 확인한다.
- `errorCode == "0"`이 정상이다. 오류는 502가 아니라 **입력 문제는 422로 바꿔** 돌려준다: `E0005`(검색어 없음), `E0006`(시도명만), `E0008`(한 글자), `E0009`(숫자만), `E0010`(너무 김: 한글 40자·영숫자 80자 초과), `E0011`(숫자 10자리 초과), `E0012`(특수문자+숫자만), `E0013`(SQL 예약어·특수문자), `E0015`(결과 9천 건 초과). `E0001`(승인키 오류), `E0014`(개발키 기간 만료), `-999`(시스템 오류)는 502 `UPSTREAM_ERROR`다.
- **검색어를 걸러서 보내야 한다.** 가이드가 `% = > < [ ]`와 SQL 예약어(`OR SELECT INSERT DELETE UPDATE CREATE DROP EXEC UNION FETCH DECLARE TRUNCATE`)가 들어간 검색어를 SQL 인젝션으로 보고 **호출한 서버 IP를 차단할 수 있다**고 안내한다. `search()` 앞에서 특수문자와 예약어가 든 검색어를 거절(422)하고, 이 검사는 `search()` 하나에서만 한다.
- 개발용 승인키는 기간이 있다 (만료 시 `E0014`). 시연 직전에 만료 여부를 확인한다.

### 팜맵 조회 (`farm/infrastructure/integrations/farmmap.py`)

명세서(`getFarmmapService`, 갱신주기 연 1회) 기준:
- 호출: `GET http://apis.data.go.kr/B552895/getFarmmapService/{기능}?serviceKey=…&type=xml&…`. 키는 공공데이터포털에서 활용신청해 발급받고 URL 인코딩해서 보낸다.
- 쓰는 기능은 둘이다. `getPnuBasedFarmmapInfo?pnuCode=` → `parcels_by_pnu`, `getIdBasedFarmmapInfo?id=` → `parcel_by_id`. 좌표·반경 기반 조회와 `getIdbasedLandRegisterInfo`(팜맵 필지와 겹치는 지번 목록)는 쓰지 않는다.
- **PNU 조회는 "그 지번과 중첩되는 팜맵 필지 전체"를 돌려준다.** 명세서 예시에서 지번 하나로 7개가 왔고 이웃 지번 필지가 섞여 있었다. 한 지번이 판독이 다른 필지 여러 개로 쪼개져 있기도 하고, 필지 하나가 여러 지번과 겹치기도 한다. 그래서 `Parcel.matches_query`(필지의 `pnuLnmCd`가 조회한 PNU와 같은지), `lnm`, `land_use`를 내려줘 프론트가 구분해 보여준다. **밭의 단위는 지번이 아니라 팜맵 필지다.**
- 응답 XML의 `fmapBdcrd`는 GML `MultiPolygon`(`srsName="EPSG:5179"`)이다. `gml:coordinates`의 `x,y x,y …`를 파싱해 WKT로 만들고 `ST_GeomFromText(wkt, 5179)`로 저장한다. 파서는 순수 함수 `parse_farmmap_response(xml) -> list[FarmmapParcel]`로 만들고 **명세서 예시 XML로 테스트**한다 (키 없이 가능). 외곽(`outerBoundaryIs`)뿐 아니라 구멍(`innerBoundaryIs`)도 처리한다. 명세서 예시에는 구멍이 없어서 실제 응답에서 확인한다.
- 필드 대응: `fmapInnb` → `farmmap_id`, `pnuLnmCd` → `pnu`, `lnm` → `lnm`, `intprNm` → `land_use`(논·밭·과수·시설), `vdptYr` → `vdpt_yr`.
- 오류: `resultCode`가 `00`이 아니면 502 `UPSTREAM_ERROR`. `resultCode`는 숫자 문자열이다 (가이드 3.2 오류 코드): 1 어플리케이션 에러, 10 잘못된 요청 파라미터, 12 서비스 없음·폐기, 20 접근 거부, 22 요청 제한 초과, 30 키 미등록, 31 키 기한 만료, 32 등록되지 않은 IP, 99 기타. 모두 502 `UPSTREAM_ERROR`이고 코드는 `details.upstream_code`에 담는다. 10은 우리 요청이 틀린 것이므로 로그에 남겨 버그로 다룬다.
- **서비스가 HTTP(SSL 없음)이고 키가 URL에 실린다.** 서버 간 호출로만 쓰고 요청 URL(키 포함)을 로그에 남기지 않는다 (`httpx` 로그 레벨 주의). 오류코드 32가 있으므로 **서버의 고정 출력 IP 등록이 필요한지** 키 신청 때 확인한다.
- **팜맵은 지적도가 아니며 법적 효력이 없다** (명세서 §2). 면적과 경계는 참고값이므로 화면에 그렇게 표시해야 한다 (§10).
- 응답은 평균 600ms, 초당 50건 제한이다. 필지 조회는 병렬로 하되 동시에 8개 이하로 제한한다.

### 기상청 단기예보 (`farm/infrastructure/integrations/kma.py`)

- 호출 (활용가이드 261019 기준): `GET https://apihub.kma.go.kr/api/typ02/openApi/VilageFcstInfoService_2.0/getVilageFcst?numOfRows=…&pageNo=1&dataType=JSON&base_date=YYYYMMDD&base_time=HHMM&nx=…&ny=…` + 인증키. **인증키 파라미터 이름이 가이드 안에서 갈린다**: 요청 명세표는 `serviceKey`(공공데이터포털 발급), 예시 URL은 `authKey`다. 키를 받을 때 어느 쪽으로 발급되는지 확인하고 `kma.py` 한 곳에서만 쓴다. 활용신청은 공공데이터포털 「기상청_단기예보 조회서비스」 페이지에서 한다.
- 응답 (`dataType=JSON`도 가능, 기본값은 XML): `header.resultCode`·`resultMsg`, `body.items.item[]` = `{baseDate, baseTime, category, fcstDate, fcstTime, fcstValue, nx, ny}`, `totalCount`. 정상 코드는 명세표에 `00`, 예시 XML에는 `0`이라 둘 다 정상으로 본다. 한 시각의 값이 `category`별 행으로 따로 와서 `fcstDate+fcstTime`으로 묶는다. 최대 30 tps, 평균 응답 600ms.
- 발표 시각은 02·05·08·11·14·17·20·23시(KST)이고 API는 발표 10분 뒤(02:10, 05:10, …)부터 제공한다. `now(KST) − 10분` 이전의 가장 최근 발표 시각을 `base`로 쓰고 `issued_at`으로 내려준다. 발표 직후 구간은 1시간 간격이라 앞으로 24시간 표시에 충분하다 (연장 구간은 3시간 간격이고 쓰지 않는다).
- 쓰는 항목: `PTY`(강수형태), `PCP`(1시간 강수량), `POP`(강수확률). 앞으로 24시간을 시각별로 묶는다.
  - `PTY` 코드(단기): 없음(0), 비(1), 비/눈(2), 눈(3), 소나기(4). 프론트가 코드를 문구로 바꾼다.
  - `PCP`는 문자열이다: 강수 없음(`-`, null, 0 → 「강수없음」), 「1mm 미만」, 1.0~29.9mm는 「실수값+mm」(예 「6.2mm」), 「30.0~50.0mm」, 「50.0mm 이상」. `Weather.pcp`에 **원문 문자열을 그대로** 내려준다 (이미 그렇게 정의돼 있다).
  - `POP`은 %이고 해상 격자는 값이 마스킹(결측)될 수 있다. ±900 이상은 결측이므로 null로 내린다.
- 위치: 구역 중심점 `ST_Transform(ST_Centroid(zone.geom), 4326)` → 기상청 격자 변환(Lambert 정각원추 공식, 기상청 공개 변환 코드를 옮김) → `nx, ny`. `latlon_to_grid`는 순수 함수다. 가이드에는 변환 공식이 없고 행정구역별 격자 표(`docs/info/kma/kma_forecast_grid_latlon.xlsx`, 3,839행: 행정구역코드, 격자 X·Y, 경도·위도)만 있다. 이 표에서 몇 행(예: 서울 종로구 청운효자동 = 위도 37.5841367, 경도 126.9706519 → (60, 127))을 뽑아 표 기반 테스트한다. 표의 위경도는 행정구역 대표점이라 같은 격자 안에서만 맞는다는 점을 고려한다.
- 실패: 502 `UPSTREAM_ERROR`, `details.source = "kma"`. 판정과 무관하다.
- 저장·캐시 없음. 호출 한도가 문제 되면 (`nx`, `ny`, `base`) 키로 메모리 캐시를 붙인다 (`# ponytail:` 표시).
- "강수확률"은 기상청 용어다. 판정 문구의 금지어 검사(`확률`)는 판정 문구에만 적용한다.

### 데이터 적재 (엑셀 → JSON → DB, `catalog/infrastructure/ingest/`)

**2026-10-28 결정:** PSIS·NCPMS API는 호출하지 않는다. 팀이 두 시스템의 자료를 정리한 엑셀 7개를 쓴다 (로컬 `docs/` 바로 아래, 기준일 2026-10-05, 저장소에는 올리지 않는다). 그래서 PSIS·NCPMS 키 신청, 문자열 파서(수확 전 일수·횟수 변환), 별표 8 매핑 작업이 필요 없다 (엑셀에 이미 들어 있다).

- 단계: ① `python -m app.catalog.infrastructure.ingest.xlsx_to_json`이 `docs/*.xlsx`를 `ingest/data/*.json`으로 바꾼다 (JSON을 커밋한다). ② `python -m app.catalog.infrastructure.ingest.load`가 JSON을 DB에 넣는다. 파일 위치와 명령 이름은 제 제안이다.
- **멱등:** 적재는 해당 테이블을 전부 지우고 다시 넣는 한 트랜잭션이다. 실패하면 롤백되어 기존 데이터가 남는다. 사용자 데이터(`spray_log` 등)가 `pesticide`를 참조하므로 `pesticide`는 자연 키(품목명+상표명)로 upsert하고 지우지 않는다. 엑셀이 곧 전체 목록이라 PSIS 때의 「등록 취소 반영」 규칙은 필요 없다 (파일에서 빠진 행은 삭제된다).
- `data_asof` = 엑셀 기준일 (2026-10-05).

| 엑셀 | 내용 | 규모 | 들어갈 곳 |
|---|---|---|---|
| `1_병해충_발생시기` | 작물·병해충별 발생 월, 출처(`NCPMS 설명` 36·`PDF 경보` 15), 지역, 재배형태, 등급(예보·주의보), 근거 문장 | 51행 | 발생 시기 테이블 → `PestCard.occurrence` |
| `2_병해충_도감` | 병해충(구분 병 60·해충 56, 학명, 부위, 증상·피해, 대표 사진, 사진 출처)과 사진 시트 | 116행 + 사진 185행 | `pest`, `pest_info`, `pest_symptom`, 사진 테이블 |
| `3_병해충별_등록약` | PSIS 등록 약(회사, 최초 등록일 포함). **중복 행이 있다** (4,133행 → 고유 3,868행) | 4,133행 | `pesticide.company`·`first_reg_date`만 가져온다 (나머지는 `4_`와 같은 키) |
| `4_약사용규칙` | 작물×병해충×약(상표)×사용 방법×희석배수, **수확 전 일수·최대 횟수를 숫자로 변환**, 변환 구분, 계열 코드, 원문 | 3,870행 (배추 2,253·감자 821·토마토 796) | `registration` |
| `5_약계열` | 품목명 → 국내 계열 코드, 국제 코드(`FRAC 24`·`IRAC 28`·`미분류`·`확인`) | 652행 | `moa`, `pesticide.moa_id` |
| `6_반복규칙` | ④ 계열 반복 규칙 (대상별 최근 N번 중, 연속 N번, 시즌 최대) | 6행 | **미결** (판정 규칙 개정과 함께) |
| `7_바이러스_매개충` | 바이러스 → 매개충 → 연결할 도감 병해충, 등록약 줄 수, 앱 안내, 근거 | 12행 | `pest_vector` |

- **변환 구분 (`4_`):** `성공` 3,303행(숫자로 변환), `심을 때` 519행(정식기·파종기, 수확 전 일수 없음), `제한 없음` 41행(미생물·구리제), `확인 필요` 7행(숫자 칸 비어 있음). 이 값들을 판정에서 어떻게 다룰지는 **미결**이다 (judge_rules 개정).
- **같은 키에 규칙이 둘인 줄**(주황 줄)은 엄격한 쪽으로 판정하자는 제안이 엑셀 안내 시트에 있다. 채택 여부는 **미결**이다.
- **증상 부위 값**은 `2_`의 부위 칸이다: `덩이, 뿌리, 잎, 줄기, 벌레, 열매` (쉼표로 여러 개). `GET /crops/{id}/symptom-parts`는 이 중 그 작물에 행이 있는 값을 돌려준다.
- **`PestCard`:** `kind` = 구분(`병`/`해충`), `description` = 증상·피해, `photo_url` = 대표 사진, 사진 출처는 작물명 또는 `(대체)`·`(보충)`·`사진 없음`이다. 값이 비면 null이다 (증상 11개, 학명 22개, 사진 14개가 비어 있다). `occurrence`는 발생 시기 테이블의 발생 월·근거 문장으로 채운다 (표기 형식은 프론트와 정한다).
- **검증 (표 기반 pytest):** 변환 전후 행 수 일치, 같은 키 중복 0, `3_`과 `4_`의 (작물, 병해충, 약, 상표) 100% 일치, `5_`의 품목명이 `4_`의 약 이름을 모두 포함, `4_`의 병해충 이름이 `2_`에 있거나 「도감 없음」으로 표시, `7_`의 두 병해충 이름이 `pest`에 있음.
- 엑셀이 바뀌면 같은 두 명령을 다시 실행한다. **엑셀 원본은 저장소에 올리지 않는다** (로컬 `docs/`에만 둔다). 저장소에는 변환한 JSON만 커밋하므로 엑셀 없이도 적재할 수 있다. 기준일이 달라지면 `data_asof`를 고친다.

## 9. 공통 규칙

- **에러 형식:** `{"error": {"code", "message", "details?"}}`. 프론트는 `code`로 분기한다. FastAPI 기본 422도 같은 형식으로 감싼다.

  | code | HTTP |
  |---|---|
  | `UNAUTHORIZED` | 401 |
  | `USERNAME_TAKEN` | 409 |
  | `NOT_FOUND` | 404 |
  | `VALIDATION_ERROR` | 422 |
  | `ONBOARDING_INCOMPLETE` | 422 |
  | `PARCEL_ALREADY_USED` | 409 |
  | `FIELD_ALREADY_SPLIT` | 409 |
  | `DUPLICATE_SPRAY` | 409 |
  | `UPSTREAM_ERROR` | 502 |

- **설정:** `pydantic-settings`로 환경변수를 읽는다 (`DATABASE_URL`, `JUSO_CONFM_KEY`, `FARMMAP_API_KEY`, `KMA_API_KEY`, `CORS_ORIGINS`). 누락되면 기동에 실패한다. 토큰과 키는 로그에 남기지 않는다.
- **인증:** `X-User-Id` 헤더. `core`의 `current_user`, `get_owned_field(field_id)`, `get_owned_zone(zone_id)` 의존성이 소유자 검사를 **한 곳에서** 처리한다. 헤더가 없거나 사용자가 없으면(탈퇴) 401. 보안은 최소로 한다 (시연용): 남의 `id`를 알면 접근할 수 있다.
- **DB:** 요청당 세션 1개. 첫 마이그레이션에서 `CREATE EXTENSION postgis`.
- **날짜:** "오늘"은 항상 **KST**(`today_kst()`)다. 서버 시간대에 따라 ③ 횟수와 기본 살포일이 하루 어긋나는 것을 막는다.
- **CORS:** 프론트가 분리되어 있으므로 `CORSMiddleware`를 쓰고 `CORS_ORIGINS`로 허용 도메인을 지정한다.
- **계약 파일:** `openapi.json`을 저장소에 커밋한다 (`python -m app.export_openapi`로 생성). 이 파일을 바꾸는 PR은 프론트 승인이 필요하다.
- **린트:** `ruff` (포맷 + 린트).
- **테스트:**
  - `judgment/domain/rules.py`: DB 없이 표 기반 pytest. 케이스 원본은 `farmguardian_judge_rules.md` §9.
  - `farm/domain/split.py`: 표 기반 pytest. 직사각형 2등분, 6:4, L자 밭, 기울어진 밭, 구멍 있는 밭, 비율 1개.
  - 연동·팜맵 파서·`latlon_to_grid`·예보 파서: §8의 fixture(명세서 예시 응답 포함)와 표 기반 pytest.
  - 데이터 적재 (테스트 DB): 같은 JSON을 두 번 적재 = 변화 없음, 중간 오류는 롤백되어 기존 행 유지, §8 「검증」 항목.
  - API: `TestClient` + **실제 PostGIS 테스트 DB** (`ST_*` 때문에 SQLite 불가). 테스트마다 트랜잭션 롤백. 밭 생성 409, 분할 결정성(미리보기 = 생성 결과), `FIELD_ALREADY_SPLIT`, 밭 삭제 CASCADE, 기록 재시도(같은 `request_id`)·중복 409, `planted_at` 변경 시 `history_confirmed` 초기화, 온보딩 완료 422·멱등, 회원 탈퇴 CASCADE·탈퇴 후 401, 가입(중복 아이디 409, 필지 조회 실패 시 사용자 미생성), 로그인 실패 401을 여기서 다룬다.
  - 문구 검사: `message`·`notices` 템플릿에 금지어(`추천 예측 예상 가능성 위험 확률 안전 문제없`)가 없는지 스캔.
  - S3에 e2e 스모크 1개 (데모 시드 기준).
- **개발용 사용자 (S1):** 가입 API(S3) 전에도 프론트와 백엔드가 `X-User-Id`로 진행할 수 있도록, S1에 사용자 하나(아이디 `dev`)를 만드는 시드를 먼저 둔다 (`python -m app.seed_demo --dev-user`, 밭·구역 없이 사용자만). 프론트는 이 사용자의 `id`를 고정 헤더로 쓴다.
- **데모 데이터:** `python -m app.seed_demo`가 데모 계정(아이디 `demo`)과 배추 밭·구역, 시연 사례별 이력을 넣고 그 계정의 `id`를 출력한다. 실제 농가 기록과 계정으로 구분된다. 사례: 통과, 같은 계통 반복(④ 주의), 횟수 소진(③ 불가), 누락 확인 전(③④ 확인 필요), 병해충 미선택. 약제와 이력은 PSIS 적재 후 배추·배추좀나방 실제 행으로 확정한다 (PRD §4.3).

## 10. 미결 사항

판정 규칙의 미결은 `farmguardian_judge_rules.md` §10이 원본이다. 여기에는 구조·일정에 영향을 주는 것만 둔다.

**닫힌 것** (2026-10-04): ② 수확 가능일 표시, ③ 품목명 기준, ④ 임계값(3회 중 2회)과 `moa` NULL 기본안, 편중도 작기 창, 대안 규칙, 문구, PSIS 데이터 형태 대부분.

**닫힌 것** (2026-10-11, PRD 반영): 지원 작물(감자·배추·토마토, 모두 일년생), 구역 모델(밭 도형 분할, 프론트는 균등·비율 분할까지), 정식일 선택, 「누락 없음」 확인, 병해충 미지목 시 ① 확인 필요, 상태 코드 이름, ③ 남은 횟수 표시, 체크별 근거 항상 제공, 날씨 범위(별도 호출·저장 없음), 병해충 이름 검색·매개충, 기록 재시도·중복 확인, 수동 구역·이력 수정·사후 분할 삭제, 일정 원칙(P0 고정·기간 연장 가능), 화면 구조(탭 4개)·첫 사용 온보딩·회원 탈퇴, 「누락 없음」을 묻는 시점(온보딩의 과거 살포 입력, 이후 조회수정 탭).

**남은 것**
1. **성분 단위 합산 여부.** 틀리면 "가능"이 잘못 나오는 위험한 방향이다. **출시 전 확인.**
2. **엑셀 데이터 검수 (S1).** PSIS·NCPMS API 조사는 엑셀 적재로 대체했다 (§8). 스키마 동결 전에 `확인 필요` 7행, 같은 키에 규칙이 둘인 줄, 도감에 없는 병해충 13개, 비어 있는 증상·사진을 확인한다. 판정 규칙 항목(judge_rules §10-3·§10-7)은 엑셀 변환 결과로 다시 본다.
3. **다작용점 약제의 ④ 제외 여부.** 농학 전문가 확인.
4. **면책 문구.** 제품·법무 확인.
5. **별표 8 매핑표** (한글 작용기작 기호 → FRAC·IRAC) 담당과 전달 시점.
6. **프론트와 합의:** 「상태 요약」의 의미 (`last_spray` + `last_judgment`로 가정, 오래된 판정이 현재 상태처럼 보이는 위험), 편중도 화면(작기 비율), 대안·약제 목록 묶음 방식, 필지 선택 화면 (`matches_query`·`used_by_field_id` 표시), **분할 방향 표현**(긴 변 기준 `crosswise`/`lengthwise`), 정식일 라벨(감자는 옮겨심지 않으므로 「심은 날」 검토), 매개충 안내 고정 문구, 날씨 표시와 실패 상태, 밭 삭제 확인, 기록 중복 409 화면.
7. **외부 확인:** 도로명주소·팜맵·기상청 키. 팜맵 최신성은 명세서 예시의 영상촬영년도가 2016이라 실제 응답의 `vdptYr`로 확인한다. 공공데이터포털 팜맵·기상청 키의 일일 호출 한도.
8. **병해충 이름 연결.** 엑셀 `2_`의 이름과 `3_`·`4_`의 이름이 같아야 한다 (적재 검증, §8). 도감에 없는 병해충은 사진·증상이 「없음」이다.
9. **서버 고정 출력 IP.** 팜맵 오류코드 32(등록되지 않은 IP)가 있다. 필요하면 배포 환경에서 고정 IP를 마련해 키 신청 때 등록한다.
10. **팜맵 면적·경계 안내 문구.** PRD는 「실제 경작 경계」라고 부르지만 지적도가 아니고 법적 효력이 없는 참고값이다. 화면 표시 방법을 면책 문구와 함께 정한다.
11. **매개충 자료.** 엑셀 `7_바이러스_매개충`(12행)으로 대체했다. 근거 문구와 등록약 0줄인 벌레의 안내(상담 안내)만 확인한다.
12. **팜맵에 없는 밭.** 수동 구역을 뺐으므로 팜맵이 필지를 돌려주지 않는 밭은 등록할 수 없다. S1 금요일 실호출에서 확인하고, 문제가 크면 수동 구역을 다시 검토한다.

## 11. 착수 전 준비물

- git 저장소와 원격(`origin`)은 준비됐다 (2026-10-05).
- `docker-compose`로 `postgis/postgis` 개발 DB (팀원 S1 첫 작업).
- 1일차 신청: 도로명주소 API 승인키, **팜맵 조회 API**(공공데이터포털 활용신청, 서버 고정 IP 등록이 필요한지 확인), **기상청 단기예보 조회서비스**(공공데이터포털 활용신청). PSIS·NCPMS 키는 엑셀 적재로 대체해 신청하지 않는다.

## 12. 다른 문서에 반영된 변경점

2026-10-04:
- `farmguardian_flow_spec.md`: §4 면적 "신발끈 공식" → `ST_Area`, §3에 `farmguardian_judge_rules.md` 우선 안내, Setup·Edit에 구역 분할, §2에 팜맵 PNU 조회가 중첩 필지를 돌려준다는 설명.
- `farmguardian_team_plan.md`: 팀원 S2 "신발끈 면적 함수" → 필지 저장·조회 쿼리(`ST_*`), PSIS 파서·팜맵 GML 파서(S1), 구역 분할 API(S2 생성 시, S3 사후), 팀장 S3 `copy_history`, 1일차 신청에 팜맵·카카오·PSIS·NCPMS 추가, `git init`·docker-compose를 S1에 추가, 위험표·미확정 갱신, **담당 재배분** (팜맵·구역 만들기 = 팀원, 나머지 = 팀장).

2026-10-11 (PRD 반영):
- `farmguardian_judge_rules.md`: ① 미지목 = 확인 필요, ③ 정식일 없음·누락 확인 전 = 확인 필요, ③ 남은 횟수 문구, ④ 누락 확인 전 = 확인 필요·비교 기록(`window`)·근거, 근거와 `data_asof` 항상 제공(`psis_asof`), 다년생 분기 삭제, 편중도 정식일 없음 처리, 테스트 표 갱신, §10-7 사용 시기 조건.
- `farmguardian_flow_spec.md`: Setup을 밭 만들기 → 구역 나누기로, 직접 입력 삭제, 병해충 이름 검색·매개충, 날씨, 기록 재시도·중복, 누락 확인, 판정 규칙 요약 갱신.
- `farmguardian_team_plan.md`: 6주 계획(P0 고정·기간 연장), 담당 재배분(기상청·도형 분할 = 팀원), 컷 목록을 P0 내 단순화 순서로, 위험표·미확정 갱신.
- `farmguardian_architecture_outline.txt`: 전체 갱신.
- `farmguardian_prd_feedback.md`: 신규. PRD에 보낼 수정 제안.
- 이 문서 §8: PSIS 적재에 등록 취소 반영(응답에서 빠진 `registration` 행 삭제, 급감·0건·오류 시 롤백) 추가.
- `farmguardian_team_plan.md`: 스프린트 3개(2주 가정)로 재작성, 담당 이름(준혁·혜빈님·DB) 반영, 작업 배정은 백로그 엑셀 기준. 이 문서 §9의 e2e 시점을 S3로.
- 화면 구조(탭 4개: 홈·병해충·조회수정·프로필)와 첫 사용 온보딩, 회원 탈퇴 반영: 이 문서 §2·§5(`users.onboarded_at`, users CASCADE)·§7(`GET /me`, `POST /me/onboarding`, `DELETE /me`, `ZoneSummary.history_confirmed`, `ONBOARDING_INCOMPLETE`)·§8(카카오 연결 끊기), flow_spec §1, team_plan §3·§4, outline, prd_feedback, 백로그 엑셀.

2026-10-28 (해커톤 시연용 인증 단순화):
- 카카오 로그인·JWT를 빼고 아이디·비밀번호 가입·로그인으로 바꿨다. 가입 때 필지를 등록해 첫 밭을 만든다. 사용자는 `X-User-Id` 헤더로 식별한다. 이 문서 §2·§3·§4·§5(`users`)·§7(`/auth/signup`, `/auth/login`, `USERNAME_TAKEN`, 가입 규칙)·§8(카카오 삭제)·§9(설정·인증·테스트·데모 시드)·§11을 고쳤다.
- 같이 고친 문서: `farmguardian_flow_spec.md`(온보딩 1단계·프로필), `farmguardian_team_plan.md`(스택·담당·키 신청·스프린트·협업 규칙), `farmguardian_architecture_outline.txt`, `farmguardian_prd_feedback.md`(#1·#9·#10), 백로그 엑셀 BE(BE-02·15·17·19)·FE(FE-06).

2026-10-28 (DDD 구조):
- 도로명주소 검색 API 가이드와 기상청 단기예보 활용가이드(261019)를 받아 §8을 확정했다: 도로명주소 요청·응답·오류 코드·검색어 필터링, 기상청 호출 URL·응답 모양·`PTY`·`PCP` 표기. 인증키 파라미터 이름(`serviceKey` 대 `authKey`)은 키 발급 때 확인한다.
- **PSIS·NCPMS API 적재를 엑셀 7개(`docs/*.xlsx`) → JSON → DB 적재로 대체했다 (§2·§3·§4·§5·§8·§9·§11). 아래 NCPMS 매뉴얼 항목은 이 결정 전에 쓴 이력이다.**
- NCPMS 매뉴얼을 받아 §8 NCPMS 적재를 확정했다: 쓰는 서비스 5개(`SVC01`·`SVC03` 목록, `SVC13` 부위 검색, `SVC05`·`SVC07` 상세), 필수 `serviceType`, 페이지 한도(50건·시작 500), 증상 부위 8개 값, 작물 코드, `pest_info` 필드 매핑. API 응답 모양(`PestCard`)은 바뀌지 않았다.
- 코드 구조를 기능별 모듈에서 DDD(바운디드 컨텍스트 5개 × 4층)로 바꿨다. 이 문서 §2(코드 구조)·§3·§4·§7(컨텍스트 열)·§8(파일 경로)·§9(테스트 대상 경로)와 `farmguardian_judge_rules.md`(파일 경로), `farmguardian_team_plan.md`(담당·서비스 이름), `farmguardian_architecture_outline.txt`(Module)를 고쳤다. 기존 `fields`·`zones`는 `farm`으로, `pests`·`ingest`와 약제 조회는 `catalog`로, `judge`는 `judgment`로, `records`는 `spraying`으로, `auth`는 `identity`로 옮겼다.
