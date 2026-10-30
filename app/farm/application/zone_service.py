from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.catalog.presentation.schemas import pesticide_base
from app.core.errors import AppError
from app.farm.infrastructure.field_repository import geojson
from app.farm.infrastructure.split_repository import existing_crop_ids, piece_sql
from app.judgment.application import reader
from app.spraying.application import spray_service


def _last_spray(db: Session, zone_id: int) -> dict | None:
    _, views = spray_service.list_sprays(db, zone_id, limit=1)  # 최근순
    if not views:
        return None
    spray = views[0].spray
    return {
        "id": spray.id,
        "pesticide": pesticide_base(views[0].pesticide).model_dump(),
        "sprayed_on": spray.sprayed_on,
        "source": spray.source,
    }


def summaries(db: Session, field_ids: list[int]) -> dict[int, list[dict]]:
    """밭 id → 구역 요약 (id 순). 구역이 없는 밭은 빠진다."""
    rows = db.execute(
        text(
            "SELECT z.id, z.field_id, z.name, z.planted_at, z.history_confirmed, "
            "c.id AS crop_id, c.name AS crop_name, "
            "round(ST_Area(z.geom)::numeric, 1) AS area_m2, ST_AsGeoJSON(z.geom, 1) AS geojson "
            "FROM zone z JOIN crop c ON c.id = z.crop_id "
            "WHERE z.field_id = ANY(:ids) ORDER BY z.id"
        ),
        {"ids": field_ids},
    ).all()
    last_judgments = reader.last_judgments(db, [row.id for row in rows])  # 한 번에 조회
    result = defaultdict(list)
    for row in rows:
        result[row.field_id].append(
            {
                "id": row.id,
                "name": row.name,
                "crop": {"id": row.crop_id, "name": row.crop_name},
                "planted_at": row.planted_at,
                "history_confirmed": row.history_confirmed,
                "area_m2": float(row.area_m2),
                "geometry": geojson(row.geojson),
                "last_spray": _last_spray(db, row.id),
                "last_judgment": last_judgments.get(row.id),
            }
        )
    return dict(result)


def _zone(row) -> dict:
    return {
        "id": row.id,
        "field_id": row.field_id,
        "name": row.name,
        "crop": {"id": row.crop_id, "name": row.crop_name},
        "planted_at": row.planted_at,
        "history_confirmed": row.history_confirmed,
        "area_m2": float(row.area_m2),
        "geometry": geojson(row.geojson),
        "bbox": [float(v) for v in (row.minx, row.miny, row.maxx, row.maxy)],
    }


def get_zones(db: Session, zone_ids: list[int]) -> list[dict]:
    """Zone 응답 (id 순)."""
    rows = db.execute(
        text(
            "SELECT z.id, z.field_id, z.name, z.planted_at, z.history_confirmed, "
            "c.id AS crop_id, c.name AS crop_name, "
            "round(ST_Area(z.geom)::numeric, 1) AS area_m2, ST_AsGeoJSON(z.geom, 1) AS geojson, "
            "round(ST_XMin(z.geom)::numeric, 1) AS minx, "
            "round(ST_YMin(z.geom)::numeric, 1) AS miny, "
            "round(ST_XMax(z.geom)::numeric, 1) AS maxx, "
            "round(ST_YMax(z.geom)::numeric, 1) AS maxy "
            "FROM zone z JOIN crop c ON c.id = z.crop_id WHERE z.id = ANY(:ids) ORDER BY z.id"
        ),
        {"ids": zone_ids},
    ).all()
    return [_zone(row) for row in rows]


def create_many(db: Session, field_id: int, user_id: int, parts: list[dict]) -> list[dict]:
    """parts = [{name, crop_id, planted_at, strip}] (분할 순서). 커밋하지 않는다."""
    zone_ids = [
        db.scalar(
            text(
                "INSERT INTO zone (field_id, user_id, name, crop_id, planted_at, geom) "
                f"SELECT f.id, :uid, :name, :crop_id, :planted_at, {piece_sql(':strip')} "
                "FROM field f WHERE f.id = :fid RETURNING id"
            ),
            {"fid": field_id, "uid": user_id, **part},
        )
        for part in parts
    ]
    return get_zones(db, zone_ids)


def check_values(
    db: Session, entries: list[tuple[list, int | None, date | None]], today: date
) -> None:
    """(오류 위치 앞부분, crop_id, planted_at)마다 없는 작물·미래 정식일을 모아 422로 알린다.

    정식일 이후 살포만 세므로 미래 정식일은 기록을 하나도 세지 않게 된다 (판정 ③).
    """
    known = existing_crop_ids(db, [crop for _, crop, _ in entries if crop is not None])
    errors = []
    for loc, crop_id, planted_at in entries:
        if crop_id is not None and crop_id not in known:
            errors.append(
                {"loc": [*loc, "crop_id"], "msg": "없는 작물입니다", "type": "not_found"}
            )
        if planted_at is not None and planted_at > today:
            errors.append(
                {
                    "loc": [*loc, "planted_at"],
                    "msg": "정식일은 오늘 이후일 수 없습니다",
                    "type": "value_error",
                }
            )
    if errors:
        raise AppError("VALIDATION_ERROR", 422, "요청 값이 올바르지 않습니다", {"errors": errors})


def update_zone(db: Session, zone_id: int, changes: dict, today: date) -> dict:
    """changes = 보낸 값만 (name, crop_id, planted_at, history_confirmed). 커밋하지 않는다."""
    check_values(db, [(["body"], changes.get("crop_id"), changes.get("planted_at"))], today)
    current = db.execute(
        # 동시 수정에서 한쪽 변경이 사라지지 않게 행을 잠그고 읽는다
        text(
            "SELECT name, crop_id, planted_at, history_confirmed FROM zone "
            "WHERE id = :id FOR UPDATE"
        ),
        {"id": zone_id},
    ).one()
    crop_id = changes.get("crop_id", current.crop_id)
    planted_at = current.planted_at
    if crop_id != current.crop_id:
        planted_at = None  # 작물이 바뀌면 새 작기다. 정식일은 보낸 값, 없으면 비운다
    planted_at = changes.get("planted_at", planted_at)
    confirmed = current.history_confirmed
    if planted_at != current.planted_at:
        confirmed = False  # 세는 기간이 바뀌어 「누락 없음」을 다시 확인받는다
    confirmed = changes.get("history_confirmed", confirmed)
    db.execute(
        text(
            "UPDATE zone SET name = :name, crop_id = :crop_id, planted_at = :planted_at, "
            "history_confirmed = :confirmed WHERE id = :id"
        ),
        {
            "id": zone_id,
            "name": changes.get("name", current.name),
            "crop_id": crop_id,
            "planted_at": planted_at,
            "confirmed": confirmed,
        },
    )
    return get_zones(db, [zone_id])[0]


@dataclass(frozen=True)
class WgsPoint:
    lon: float  # 경도
    lat: float  # 위도


def centroid_wgs84(db: Session, zone_id: int) -> WgsPoint:
    """날씨(기상청 격자 변환)가 쓰는 구역 중심점. 소유자 확인은 호출하는 쪽이 한다."""
    row = db.execute(
        text(
            "SELECT ST_X(p) AS lon, ST_Y(p) AS lat FROM "
            "(SELECT ST_Transform(ST_Centroid(geom), 4326) AS p FROM zone WHERE id = :id) q"
        ),
        {"id": zone_id},
    ).one_or_none()
    if row is None:
        raise AppError("NOT_FOUND", 404, "찾을 수 없습니다")
    return WgsPoint(row.lon, row.lat)
