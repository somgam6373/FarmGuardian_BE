import pytest
from sqlalchemy import text

from app.core.errors import AppError
from app.farm.application import zone_service

# 실제 팜맵 필지(161-3) 근처의 EPSG:5179 좌표
X, Y = 993840.0, 1970360.0


def test_centroid_matches_postgis_transform(db, make_user, make_field, make_zone):
    uid = make_user("farmer")
    zone_id = make_zone(make_field(uid), uid)
    db.execute(
        text(
            "UPDATE zone SET geom = ST_Multi(ST_MakeEnvelope(:x, :y, :x2, :y2, 5179)) "
            "WHERE id = :id"
        ),
        {"x": X, "y": Y, "x2": X + 10, "y2": Y + 10, "id": zone_id},
    )
    point = zone_service.centroid_wgs84(db, zone_id)
    lon, lat = db.execute(
        text(
            "SELECT ST_X(p), ST_Y(p) FROM "
            "(SELECT ST_Transform(ST_SetSRID(ST_Point(:x, :y), 5179), 4326) AS p) q"
        ),
        {"x": X + 5, "y": Y + 5},
    ).one()
    assert point.lon == pytest.approx(lon, abs=1e-9)
    assert point.lat == pytest.approx(lat, abs=1e-9)
    assert 126 < point.lon < 130 and 33 < point.lat < 39


def test_unknown_zone_is_404(db):
    with pytest.raises(AppError) as error:
        zone_service.centroid_wgs84(db, 999999999)
    assert error.value.status == 404
