import json

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.farm.domain.geometry import MultiPolygon, Ring
from app.farm.infrastructure.field_repository import geojson


def piece_sql(strip: str) -> str:
    """밭(f.geom)을 띠(WKT를 담은 SQL 식)로 자른 구역 도형. 미리보기와 구역 저장이 같이 쓴다."""
    return (
        "ST_Multi(ST_CollectionExtract("
        f"ST_Intersection(f.geom, ST_GeomFromText({strip}, 5179)), 3))"
    )


def _points(coordinates) -> Ring:
    return [(x, y) for x, y in coordinates]


def field_shape(db: Session, field_id: int) -> tuple[MultiPolygon, Ring]:
    """밭 도형과 최소 회전 사각형의 바깥 링 (좌표 정밀도 그대로)."""
    row = db.execute(
        text(
            "SELECT ST_AsGeoJSON(geom) AS shape, "
            "ST_AsGeoJSON(ST_OrientedEnvelope(geom)) AS envelope FROM field WHERE id = :id"
        ),
        {"id": field_id},
    ).one()
    shape = json.loads(row.shape)["coordinates"]
    polygons = [[_points(ring) for ring in polygon] for polygon in shape]
    return polygons, _points(json.loads(row.envelope)["coordinates"][0])


def preview(db: Session, field_id: int, strips: list[str]) -> list[dict]:
    rows = db.execute(
        text(
            f"WITH p AS (SELECT n, {piece_sql('s')} AS g FROM field f, "
            "unnest(CAST(:strips AS text[])) WITH ORDINALITY AS u(s, n) WHERE f.id = :id) "
            "SELECT round(ST_Area(g)::numeric, 1) AS area_m2, ST_AsGeoJSON(g, 1) AS geojson "
            "FROM p ORDER BY n"
        ),
        {"id": field_id, "strips": strips},
    ).all()
    return [{"geometry": geojson(r.geojson), "area_m2": float(r.area_m2)} for r in rows]


def lock_field_has_zones(db: Session, field_id: int) -> bool:
    """밭 행을 잠그고 (동시 구역 생성 방지) 구역이 이미 있는지 돌려준다."""
    db.execute(text("SELECT 1 FROM field WHERE id = :id FOR UPDATE"), {"id": field_id})
    return db.scalar(
        text("SELECT EXISTS (SELECT 1 FROM zone WHERE field_id = :id)"), {"id": field_id}
    )


def existing_crop_ids(db: Session, crop_ids: list[int]) -> set[int]:
    rows = db.scalars(text("SELECT id FROM crop WHERE id = ANY(:ids)"), {"ids": crop_ids})
    return set(rows)
