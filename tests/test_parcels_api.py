import pytest
from fastapi.testclient import TestClient

from app.core.errors import AppError
from app.farm.infrastructure import field_repository
from app.farm.infrastructure.integrations import farmmap
from app.farm.infrastructure.integrations.farmmap import FarmmapParcel
from app.main import app
from tests.farm_support import square

PNU = "4182032521101610003"
SQUARE = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)]

client = TestClient(app)


def _parcel(farmmap_id: str, pnu: str, polygons) -> FarmmapParcel:
    return FarmmapParcel(farmmap_id, pnu, "161-3전", "밭", 2022, polygons)


@pytest.fixture
def farmmap_calls(monkeypatch):
    calls = []

    def fake(pnu):
        calls.append(pnu)
        return [
            _parcel("1", PNU, [[SQUARE]]),
            _parcel("2", "4182032521101600007", [[SQUARE]]),
        ]

    monkeypatch.setattr(farmmap, "parcels_by_pnu", fake)
    return calls


def test_returns_spec_shaped_parcels(farmmap_calls):
    r = client.get("/parcels", params={"pnu": PNU})

    assert r.status_code == 200
    first, second = r.json()
    assert first == {
        "farmmap_id": "1",
        "pnu": PNU,
        "lnm": "161-3전",
        "land_use": "밭",
        "vdpt_yr": 2022,
        "area_m2": 100.0,
        "geometry": {"type": "MultiPolygon", "coordinates": [[[list(p) for p in SQUARE]]]},
        "matches_query": True,
        "used_by_field_id": None,
    }
    assert second["matches_query"] is False
    assert farmmap_calls == [PNU]


def test_coordinates_and_area_rounded_to_one_decimal(monkeypatch):
    ring = [(0.04, 0.0), (993833.485, 0.0), (993833.485, 1.0), (0.04, 1.0), (0.04, 0.0)]
    monkeypatch.setattr(farmmap, "parcels_by_pnu", lambda pnu: [_parcel("1", PNU, [[ring]])])

    [parcel] = client.get("/parcels", params={"pnu": PNU}).json()

    assert parcel["geometry"]["coordinates"][0][0][0] == [0.0, 0.0]
    assert parcel["geometry"]["coordinates"][0][0][1] == [993833.5, 0.0]
    assert parcel["area_m2"] == 993833.4


@pytest.mark.parametrize("pnu", ["123", "418203252110161000a", "41820325211016100031"])
def test_bad_pnu_is_validation_error(farmmap_calls, pnu):
    r = client.get("/parcels", params={"pnu": pnu})

    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert farmmap_calls == []


def test_missing_pnu_is_validation_error(farmmap_calls):
    r = client.get("/parcels")

    assert r.status_code == 422
    assert farmmap_calls == []


def test_upstream_error_is_502(monkeypatch):
    def fail(pnu):
        raise AppError("UPSTREAM_ERROR", 502, "팜맵 조회에 실패했습니다", {"source": "farmmap"})

    monkeypatch.setattr(farmmap, "parcels_by_pnu", fail)

    r = client.get("/parcels", params={"pnu": PNU})

    assert r.status_code == 502
    assert r.json()["error"]["code"] == "UPSTREAM_ERROR"
    assert r.json()["error"]["details"] == {"source": "farmmap"}


def _used_by(response) -> dict:
    return {p["farmmap_id"]: p["used_by_field_id"] for p in response.json()}


def test_used_by_field_id_with_header(client, db, make_user, farmmap_calls):
    uid = make_user("farmer")
    field_id = field_repository.insert_field(db, uid, "f", [square("1")])
    response = client.get("/parcels", params={"pnu": PNU}, headers={"X-User-Id": str(uid)})
    assert response.status_code == 200
    assert _used_by(response) == {"1": field_id, "2": None}


def test_other_users_field_not_shown(client, db, make_user, farmmap_calls):
    me, other = make_user("me"), make_user("other")
    field_repository.insert_field(db, other, "f", [square("1")])
    response = client.get("/parcels", params={"pnu": PNU}, headers={"X-User-Id": str(me)})
    assert _used_by(response) == {"1": None, "2": None}


@pytest.mark.parametrize("header", ["abc", "999999999"])
def test_bad_header_is_401(client, farmmap_calls, header):
    response = client.get("/parcels", params={"pnu": PNU}, headers={"X-User-Id": header})
    assert response.status_code == 401
