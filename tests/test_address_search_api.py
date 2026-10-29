import pytest
from fastapi.testclient import TestClient

from app.core.errors import AppError
from app.farm.infrastructure.integrations import vworld
from app.farm.infrastructure.integrations.vworld import VworldLot
from app.main import app

client = TestClient(app)


@pytest.fixture
def vworld_calls(monkeypatch):
    calls = []

    def fake(keyword, page):
        calls.append((keyword, page))
        return 29, [VworldLot("4182032521101610003", "경기도 가평군 청평면 청평리 161-3")]

    monkeypatch.setattr(vworld, "search_parcels", fake)
    return calls


def test_returns_spec_shape(vworld_calls):
    r = client.get("/addresses/search", params={"keyword": "청평리 161-3"})

    assert r.status_code == 200
    item = {"jibun_addr": "경기도 가평군 청평면 청평리 161-3", "pnu": "4182032521101610003"}
    assert r.json() == {"total": 29, "items": [item]}
    assert vworld_calls == [("청평리 161-3", 1)]


def test_keyword_is_trimmed(vworld_calls):
    client.get("/addresses/search", params={"keyword": "  청평리 161  "})

    assert vworld_calls == [("청평리 161", 1)]


def test_page_is_passed(vworld_calls):
    client.get("/addresses/search", params={"keyword": "청평리 161", "page": 3})

    assert vworld_calls == [("청평리 161", 3)]


@pytest.mark.parametrize(
    "keyword",
    [
        "청",
        "가" * 81,
        "   ",
        "161-3",
        "청평리'",
        "청평리 <b>",
        "청평리%",
        "淸平里",
        "cheongpyeong 161",
    ],
)
def test_invalid_keyword_is_422(vworld_calls, keyword):
    r = client.get("/addresses/search", params={"keyword": keyword})

    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert vworld_calls == []


@pytest.mark.parametrize("page", ["0", "1001", "abc"])
def test_invalid_page_is_422(vworld_calls, page):
    r = client.get("/addresses/search", params={"keyword": "청평리 161", "page": page})

    assert r.status_code == 422
    assert vworld_calls == []


def test_missing_keyword_is_422(vworld_calls):
    r = client.get("/addresses/search")

    assert r.status_code == 422
    assert vworld_calls == []


def test_upstream_error_is_502(monkeypatch):
    def fail(keyword, page):
        raise AppError("UPSTREAM_ERROR", 502, "주소 검색에 실패했습니다", {"source": "vworld"})

    monkeypatch.setattr(vworld, "search_parcels", fail)

    r = client.get("/addresses/search", params={"keyword": "청평리 161"})

    assert r.status_code == 502
    assert r.json()["error"]["details"] == {"source": "vworld"}
