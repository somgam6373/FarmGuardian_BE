-- FarmGuardian DB 스키마 (PostgreSQL + PostGIS)
-- 실행: psql -d farmguardian -f schema.sql   (빈 DB에서 한 번. 다시 만들 때는 DB를 지우고 시작한다)
-- 근거: docs/dev/팜가디언_아키텍처.md §5, 팜가디언_API_명세.md, 팜가디언_판정_규칙.md

BEGIN;

CREATE EXTENSION IF NOT EXISTS postgis;

-- ============================================================
-- 사용자
-- ============================================================
CREATE TABLE users (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username      text        NOT NULL UNIQUE,
    password_hash text        NOT NULL,
    onboarded_at  timestamptz,                          -- 온보딩 완료 시각. NULL = 미완료
    created_at    timestamptz NOT NULL DEFAULT now()
);

-- ============================================================
-- 참고 데이터 (엑셀 7개를 JSON으로 바꿔 적재. 사용자 데이터가 참조하므로 pesticide·pest·crop은 지우지 않고 upsert)
-- ============================================================
CREATE TABLE crop (
    id   int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL UNIQUE
);

-- 작용기작. label_kr = 국내 계열 코드(복합제는 '카+가1'), system·code = 5_약계열의 'FRAC 24'를 나눈 값
CREATE TABLE moa (
    id       int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    label_kr text NOT NULL UNIQUE,
    system   text,
    code     text
);

-- 약제 = 품목명 + 상표명. 같은 품목의 다른 상표는 다른 행 (횟수는 item_name으로 합산)
CREATE TABLE pesticide (
    id        int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    item_name text NOT NULL,
    name      text NOT NULL,
    use_name  text,                                     -- 용도: 살충·살균·균충
    moa_id    int REFERENCES moa (id),
    UNIQUE (item_name, name)
);
CREATE INDEX pesticide_item_name_idx ON pesticide (item_name);

CREATE TABLE pest (
    id              int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name            text NOT NULL UNIQUE,
    kind            text CHECK (kind IN ('병', '해충')),   -- 엑셀 2_병해충_도감의 구분. 도감에 없으면 NULL
    scientific_name text
);

-- 작물별 도감 정보 (PestCard)
CREATE TABLE pest_info (
    pest_id      int  NOT NULL REFERENCES pest (id),
    crop_id      int  NOT NULL REFERENCES crop (id),
    description  text,                                  -- 증상·피해
    photo_url    text,
    photo_source text,                                  -- 작물명 / '양배추(대체)' / '옥수수(보충)'
    PRIMARY KEY (pest_id, crop_id)
);

CREATE TABLE pest_photo (
    id       int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pest_id  int  NOT NULL REFERENCES pest (id),
    crop_id  int  NOT NULL REFERENCES crop (id),
    title    text,
    part     text,
    url      text NOT NULL
);
CREATE INDEX pest_photo_pest_crop_idx ON pest_photo (pest_id, crop_id);

-- 증상 부위 → 병해충 후보 (덩이·뿌리·잎·줄기·벌레·열매)
CREATE TABLE pest_symptom (
    pest_id int  NOT NULL REFERENCES pest (id),
    crop_id int  NOT NULL REFERENCES crop (id),
    part    text NOT NULL,
    PRIMARY KEY (pest_id, crop_id, part)
);
CREATE INDEX pest_symptom_crop_part_idx ON pest_symptom (crop_id, part);

-- 발생 시기 (엑셀 1_병해충_발생시기). PestCard.occurrence와 occurrence_source를 만든다
CREATE TABLE pest_occurrence (
    id               int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pest_id          int NOT NULL REFERENCES pest (id),
    crop_id          int NOT NULL REFERENCES crop (id),
    months           smallint[] NOT NULL DEFAULT '{}',  -- 발생 월
    source           text,                              -- 'NCPMS 설명' / 'PDF 경보'
    region           text,
    cultivation_type text,
    grade            text,                              -- 예보 / 주의보
    basis_text       text                               -- 근거 문장
);
CREATE INDEX pest_occurrence_pest_crop_idx ON pest_occurrence (pest_id, crop_id);

-- 바이러스 → 매개충 (엑셀 7_바이러스_매개충). 매개충도 pest 행이다
CREATE TABLE pest_vector (
    virus_pest_id  int  NOT NULL REFERENCES pest (id),
    vector_pest_id int  NOT NULL REFERENCES pest (id),
    crop_id        int  NOT NULL REFERENCES crop (id),
    guide          text,                                -- 앱 안내 문구
    source         text NOT NULL,                       -- 근거. 없으면 넣지 않는다
    PRIMARY KEY (virus_pest_id, vector_pest_id, crop_id)
);

-- 작물×병해충×약제×사용 방법별 사용 기준 (엑셀 4_약사용규칙, 회사·최초 등록일은 3_)
-- 같은 (작물, 병해충, 약제, 사용 방법, 희석배수)에 규칙이 둘인 줄이 있어 UNIQUE를 걸지 않는다 (판정은 엄격한 쪽을 쓴다)
CREATE TABLE registration (
    id               int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    crop_id          int  NOT NULL REFERENCES crop (id),
    pest_id          int  NOT NULL REFERENCES pest (id),
    pesticide_id     int  NOT NULL REFERENCES pesticide (id),
    use_method       text,                              -- 사용 방법 (예: 발생 초부터 경엽처리)
    dilut_raw        text,                              -- 희석배수 원문
    phi_days         int  CHECK (phi_days >= 0),        -- 수확 전 일수. NULL = 읽지 못함·해당 없음
    max_uses         int  CHECK (max_uses > 0),         -- 최대 사용 횟수
    use_suittime_raw text,                              -- 사용 시기 원문
    use_num_raw      text,                              -- 사용 횟수 원문
    usage_type       text NOT NULL DEFAULT 'NORMAL'
                     CHECK (usage_type IN ('NORMAL', 'AT_PLANTING', 'NO_LIMIT', 'CHECK')),
    note             text,
    company          text,
    first_reg_date   date,
    data_asof        date NOT NULL                      -- 엑셀 기준일 ("데이터 조회일")
);
CREATE INDEX registration_crop_pesticide_idx ON registration (crop_id, pesticide_id);
CREATE INDEX registration_crop_pest_idx ON registration (crop_id, pest_id);

-- ============================================================
-- 사용자 데이터 (좌표계 EPSG:5179 = 미터 평면, ST_Area 결과가 ㎡)
-- ============================================================
CREATE TABLE field (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id    bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    name       text   NOT NULL,
    geom       geometry(MultiPolygon, 5179) NOT NULL,   -- 고른 필지 도형의 합집합
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, user_id)                                -- 아래 복합 FK가 user_id 복사본을 일치시킨다
);
CREATE INDEX field_user_idx ON field (user_id);

CREATE TABLE field_parcel (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    field_id   bigint NOT NULL,
    user_id    bigint NOT NULL,
    farmmap_id text   NOT NULL,                         -- 팜맵 fmapInnb
    pnu        text   NOT NULL,                         -- pnuLnmCd
    lnm        text,                                    -- 지번 표기
    land_use   text,                                    -- 논·밭·과수·시설 (intprNm)
    vdpt_yr    int,                                     -- 영상 촬영 연도
    geom       geometry(MultiPolygon, 5179) NOT NULL,
    fetched_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (field_id, user_id) REFERENCES field (id, user_id) ON DELETE CASCADE,
    UNIQUE (user_id, farmmap_id)                        -- 필지는 사용자당 한 밭에만
);
CREATE INDEX field_parcel_field_idx ON field_parcel (field_id);

CREATE TABLE zone (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    field_id          bigint NOT NULL,
    user_id           bigint NOT NULL,
    name              text   NOT NULL,
    crop_id           int    NOT NULL REFERENCES crop (id),
    planted_at        date,                             -- 정식일. NULL이면 ③ 횟수는 확인 필요
    history_confirmed boolean NOT NULL DEFAULT false,   -- 「누락 없음」 확인
    geom              geometry(MultiPolygon, 5179) NOT NULL,
    FOREIGN KEY (field_id, user_id) REFERENCES field (id, user_id) ON DELETE CASCADE
);
CREATE INDEX zone_field_idx ON zone (field_id);

CREATE TABLE spray_log (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    zone_id      bigint NOT NULL REFERENCES zone (id) ON DELETE CASCADE,
    pesticide_id int    NOT NULL REFERENCES pesticide (id),
    sprayed_on   date   NOT NULL,
    source       text   NOT NULL CHECK (source IN ('manual', 'app')),
    request_id   uuid   NOT NULL UNIQUE,                -- 재시도를 한 번만 반영
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX spray_log_zone_date_idx ON spray_log (zone_id, sprayed_on DESC);

CREATE TABLE judgment (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    zone_id      bigint NOT NULL REFERENCES zone (id) ON DELETE CASCADE,
    pest_id      int    REFERENCES pest (id),           -- NULL = 병해충 미지목
    pesticide_id int    NOT NULL REFERENCES pesticide (id),
    apply_date   date   NOT NULL,
    verdict      text   NOT NULL CHECK (verdict IN ('OK', 'CAUTION', 'BLOCKED', 'NEEDS_CHECK')),
    result       jsonb  NOT NULL,                       -- 근거 원문·기준일 스냅샷
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX judgment_zone_created_idx ON judgment (zone_id, created_at DESC);

-- ============================================================
-- 고정 데이터: 지원 작물 3종
-- ============================================================
INSERT INTO crop (name) VALUES ('감자'), ('배추'), ('토마토');

COMMIT;
