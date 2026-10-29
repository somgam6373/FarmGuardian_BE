from app.farm.domain.geometry import MultiPolygon, multipolygon_area
from app.farm.infrastructure.integrations import farmmap, vworld


def _geojson(polygons: MultiPolygon) -> dict:
    # 명세: EPSG:5179 미터 좌표, 소수 1자리
    return {
        "type": "MultiPolygon",
        "coordinates": [
            [[[round(x, 1), round(y, 1)] for x, y in ring] for ring in polygon]
            for polygon in polygons
        ],
    }


def find_parcels(pnu: str) -> list[dict]:
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
            "used_by_field_id": None,  # 밭 저장(POST /fields) 전까지는 항상 없음
        }
        for p in farmmap.parcels_by_pnu(pnu)
    ]


def search_addresses(keyword: str, page: int) -> dict:
    total, lots = vworld.search_parcels(keyword, page)
    items = [{"jibun_addr": lot.jibun_addr, "pnu": lot.pnu} for lot in lots]
    return {"total": total, "items": items}
