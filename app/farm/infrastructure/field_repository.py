import json
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.farm.domain.geometry import to_wkt
from app.farm.infrastructure.integrations.farmmap import FarmmapParcel

# 면적·GeoJSON·bbox를 한 번에 읽는다. 명세대로 모두 소수 1자리
_FIELD_COLUMNS = (
    "id, name, round(ST_Area(geom)::numeric, 1) AS area_m2, ST_AsGeoJSON(geom, 1) AS geojson, "
    "round(ST_XMin(geom)::numeric, 1) AS minx, round(ST_YMin(geom)::numeric, 1) AS miny, "
    "round(ST_XMax(geom)::numeric, 1) AS maxx, round(ST_YMax(geom)::numeric, 1) AS maxy"
)


@dataclass(frozen=True)
class FieldRow:
    id: int
    name: str
    area_m2: float
    geometry: dict
    bbox: list[float]


def geojson(raw: str) -> dict:
    # 명세 모양만 남긴다 (crs 등 다른 멤버는 버린다)
    data = json.loads(raw)
    return {"type": data["type"], "coordinates": data["coordinates"]}


def _field(row) -> FieldRow:
    return FieldRow(
        id=row.id,
        name=row.name,
        area_m2=float(row.area_m2),
        geometry=geojson(row.geojson),
        bbox=[float(v) for v in (row.minx, row.miny, row.maxx, row.maxy)],
    )


def used_farmmap_ids(db: Session, user_id: int, farmmap_ids: list[str]) -> dict[str, int]:
    """이 사용자의 밭이 이미 쓰는 필지 → 그 밭 id."""
    rows = db.execute(
        text(
            "SELECT farmmap_id, field_id FROM field_parcel "
            "WHERE user_id = :uid AND farmmap_id = ANY(:ids)"
        ),
        {"uid": user_id, "ids": farmmap_ids},
    ).all()
    return {row.farmmap_id: row.field_id for row in rows}


def insert_field(db: Session, user_id: int, name: str, parcels: list[FarmmapParcel]) -> int:
    """밭(필지 합집합)과 필지 행을 저장하고 밭 id를 돌려준다. 커밋하지 않는다."""
    wkts = [to_wkt(p.polygons) for p in parcels]
    field_id = db.scalar(
        text(
            "INSERT INTO field (user_id, name, geom) "
            "SELECT :uid, :name, ST_Multi(ST_Union(ST_GeomFromText(w, 5179))) "
            "FROM unnest(CAST(:wkts AS text[])) AS w RETURNING id"
        ),
        {"uid": user_id, "name": name, "wkts": wkts},
    )
    db.execute(
        text(
            "INSERT INTO field_parcel "
            "(field_id, user_id, farmmap_id, pnu, lnm, land_use, vdpt_yr, geom) "
            "VALUES (:fid, :uid, :farmmap_id, :pnu, :lnm, :land_use, :vdpt_yr, "
            "ST_GeomFromText(:wkt, 5179))"
        ),
        [
            {
                "fid": field_id,
                "uid": user_id,
                "farmmap_id": p.farmmap_id,
                "pnu": p.pnu,
                "lnm": p.lnm,
                "land_use": p.land_use,
                "vdpt_yr": p.vdpt_yr,
                "wkt": wkt,
            }
            for p, wkt in zip(parcels, wkts)
        ],
    )
    return field_id


def list_fields(db: Session, user_id: int) -> list[FieldRow]:
    rows = db.execute(
        text(f"SELECT {_FIELD_COLUMNS} FROM field WHERE user_id = :uid ORDER BY id"),
        {"uid": user_id},
    ).all()
    return [_field(row) for row in rows]


def get_field(db: Session, field_id: int) -> FieldRow:
    row = db.execute(
        text(f"SELECT {_FIELD_COLUMNS} FROM field WHERE id = :id"), {"id": field_id}
    ).one()
    return _field(row)


def delete_field(db: Session, field_id: int) -> None:
    # 구역·필지·기록·판정은 ON DELETE CASCADE로 함께 지워진다
    db.execute(text("DELETE FROM field WHERE id = :id"), {"id": field_id})
