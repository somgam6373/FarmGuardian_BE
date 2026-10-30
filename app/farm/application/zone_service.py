from collections import defaultdict

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.catalog.presentation.schemas import pesticide_base
from app.farm.infrastructure.field_repository import geojson
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
