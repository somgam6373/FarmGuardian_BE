from collections import defaultdict

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.catalog.presentation.schemas import pesticide_base
from app.farm.infrastructure.field_repository import geojson
from app.farm.infrastructure.split_repository import piece_sql
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
                # 판정 컨텍스트에 최근 판정을 읽는 서비스가 생기면 채운다
                "last_judgment": None,
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
