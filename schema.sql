-- FarmGuardian DB 스키마 (PostgreSQL + PostGIS)
-- 실행: psql -d farmguardian -f schema.sql   (빈 DB에서 한 번. 다시 만들 때는 DB를 지우고 시작한다. 한글 Windows는 먼저 PGCLIENTENCODING=UTF8)
-- 근거: docs/dev/팜가디언_아키텍처.md §5, 팜가디언_API_명세.md, 팜가디언_판정_규칙.md, 2026-10-29-static-catalog-design.md

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
-- 작물. 나머지 참고 데이터(병해충·약제·작용기작 등)는 DB에 없고 저장소의 정적 JSON(app/catalog/data/)이다.
-- zone.crop_id가 참조하므로 crop만 DB에 둔다. id·이름은 app/catalog/data/crop.json과 같아야 한다.
-- ============================================================
CREATE TABLE crop (
    id   int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL UNIQUE
);

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
    pesticide_id int    NOT NULL,                       -- 정적 데이터의 약제 id (FK 없음)
    sprayed_on   date   NOT NULL,
    source       text   NOT NULL CHECK (source IN ('manual', 'app')),
    request_id   uuid   NOT NULL UNIQUE,                -- 재시도를 한 번만 반영
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX spray_log_zone_date_idx ON spray_log (zone_id, sprayed_on DESC);

CREATE TABLE judgment (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    zone_id      bigint NOT NULL REFERENCES zone (id) ON DELETE CASCADE,
    pest_id      int,                                   -- NULL = 병해충 미지목. 정적 데이터의 pest_id (FK 없음)
    pesticide_id int    NOT NULL,                       -- 정적 데이터의 약제 id (FK 없음)
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
