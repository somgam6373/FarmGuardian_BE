from concurrent.futures import ThreadPoolExecutor

import httpx2
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.farm.application import zone_service
from app.farm.domain.geometry import MultiPolygon, multipolygon_area, to_wkt
from app.farm.domain.split import split_strips
from app.farm.infrastructure import field_repository, split_repository
from app.farm.infrastructure.field_repository import FieldRow
from app.farm.infrastructure.integrations import farmmap, vworld
from app.farm.infrastructure.integrations.farmmap import FarmmapParcel

MAX_CONCURRENT_FETCHES = 8


def _geojson(polygons: MultiPolygon) -> dict:
    # 명세: EPSG:5179 미터 좌표, 소수 1자리
    return {
        "type": "MultiPolygon",
        "coordinates": [
            [[[round(x, 1), round(y, 1)] for x, y in ring] for ring in polygon]
            for polygon in polygons
        ],
    }


def find_parcels(pnu: str, db: Session | None = None, user_id: int | None = None) -> list[dict]:
    parcels = farmmap.parcels_by_pnu(pnu)
    # 헤더가 없으면 DB를 읽지 않고 항상 null
    used = (
        field_repository.used_farmmap_ids(db, user_id, [p.farmmap_id for p in parcels])
        if user_id is not None
        else {}
    )
    return [
        {
            "farmmap_id": p.farmmap_id,
            "pnu": p.pnu,
            "lnm": p.lnm,
            "land_use": p.land_use,
            "vdpt_yr": p.vdpt_yr,
            "area_m2": round(multipolygon_area(p.polygons), 1),
            "geometry": _geojson(p.polygons),
            "matches_query": p.pnu == pnu,
            "used_by_field_id": used.get(p.farmmap_id),
        }
        for p in parcels
    ]


def search_addresses(keyword: str, page: int) -> dict:
    total, lots = vworld.search_parcels(keyword, page)
    items = [{"jibun_addr": lot.jibun_addr, "pnu": lot.pnu} for lot in lots]
    return {"total": total, "items": items}


def _field(row: FieldRow, zones: list[dict]) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "area_m2": row.area_m2,
        "geometry": row.geometry,
        "bbox": row.bbox,
        "zones": zones,
    }


def _parcel_used(farmmap_ids: list[str]) -> AppError:
    return AppError(
        "PARCEL_ALREADY_USED", 409, "이미 다른 밭에 등록된 필지입니다", {"farmmap_ids": farmmap_ids}
    )


def _check_unused(db: Session, user_id: int, farmmap_ids: list[str]) -> None:
    used = field_repository.used_farmmap_ids(db, user_id, farmmap_ids)
    if used:
        raise _parcel_used([i for i in farmmap_ids if i in used])


def _fetch_parcels(farmmap_ids: list[str]) -> list[FarmmapParcel | None]:
    # 필지마다 평균 600ms라 직렬로 부르지 않는다. 결과는 요청 순서를 따른다
    with (
        httpx2.Client(timeout=farmmap.TIMEOUT_SECONDS) as client,
        ThreadPoolExecutor(max_workers=MAX_CONCURRENT_FETCHES) as executor,
    ):
        return list(executor.map(lambda i: farmmap.parcel_by_id(i, client=client), farmmap_ids))


def create_field(db: Session, user_id: int, name: str, farmmap_ids: list[str]) -> dict:
    """필지로 밭을 만들고 Field를 돌려준다. 커밋은 호출한 쪽이 한다 (가입도 이 함수를 쓴다)."""
    _check_unused(db, user_id, farmmap_ids)  # 팜맵 호출 전에 막는다
    parcels = _fetch_parcels(farmmap_ids)
    errors = [
        {"loc": ["body", "parcel_farmmap_ids", index], "msg": "팜맵에 없는 필지입니다",
         "type": "not_found"}
        for index, parcel in enumerate(parcels)
        if parcel is None
    ]
    if errors:
        raise AppError("VALIDATION_ERROR", 422, "요청 값이 올바르지 않습니다", {"errors": errors})
    try:
        # 동시 요청이 같은 필지를 먼저 저장했으면 이 저장만 되돌리고 409로 답한다
        with db.begin_nested():
            field_id = field_repository.insert_field(db, user_id, name, parcels)
    except IntegrityError:
        _check_unused(db, user_id, farmmap_ids)
        raise
    return _field(field_repository.get_field(db, field_id), [])


def list_fields(db: Session, user_id: int) -> list[dict]:
    rows = field_repository.list_fields(db, user_id)
    zones = zone_service.summaries(db, [row.id for row in rows])
    return [_field(row, zones.get(row.id, [])) for row in rows]


def delete_field(db: Session, field_id: int) -> None:
    field_repository.delete_field(db, field_id)


def split_strips_for(db: Session, field_id: int, direction: str, ratios: list[int]) -> list[str]:
    """밭을 자를 띠들의 WKT. 같은 입력이면 같은 결과다 (미리보기 = 구역 생성)."""
    polygons, envelope = split_repository.field_shape(db, field_id)
    return [to_wkt([[ring]]) for ring in split_strips(polygons, envelope, direction, ratios)]


def split_preview(db: Session, field_id: int, direction: str, ratios: list[int]) -> list[dict]:
    return split_repository.preview(db, field_id, split_strips_for(db, field_id, direction, ratios))


def create_zones(
    db: Session,
    field_id: int,
    user_id: int,
    direction: str,
    ratios: list[int],
    zones: list[dict],
) -> list[dict]:
    """zones = [{name, crop_id, planted_at}] (ratios 순서). 커밋은 호출한 쪽이 한다."""
    if split_repository.lock_field_has_zones(db, field_id):
        raise AppError("FIELD_ALREADY_SPLIT", 409, "이미 구역이 나뉜 밭입니다")
    known = split_repository.existing_crop_ids(db, [z["crop_id"] for z in zones])
    errors = [
        {"loc": ["body", "zones", index, "crop_id"], "msg": "없는 작물입니다", "type": "not_found"}
        for index, zone in enumerate(zones)
        if zone["crop_id"] not in known
    ]
    if errors:
        raise AppError("VALIDATION_ERROR", 422, "요청 값이 올바르지 않습니다", {"errors": errors})
    strips = split_strips_for(db, field_id, direction, ratios)
    parts = [{**zone, "strip": strip} for zone, strip in zip(zones, strips)]
    return zone_service.create_many(db, field_id, user_id, parts)
