import json
from pathlib import Path

import httpx2
import pytest

from app.core.config import settings
from app.core.errors import AppError
from app.farm.infrastructure.integrations.vworld import VworldLot, search_parcels

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _client(handler) -> httpx2.Client:
    return httpx2.Client(transport=httpx2.MockTransport(handler))


def _respond(status: int, text: str):
    return lambda request: httpx2.Response(status, text=text)


def _upstream_details(handler) -> dict:
    with pytest.raises(AppError) as exc:
        search_parcels("청평리 161", 1, client=_client(handler))
    assert exc.value.status == 502
    return exc.value.details


def test_sends_search_params():
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert str(request.url).startswith("https://api.vworld.kr/req/search?")
        assert dict(request.url.params) == {
            "service": "search",
            "request": "search",
            "version": "2.0",
            "type": "address",
            "category": "parcel",
            "crs": "epsg:5179",
            "format": "json",
            "size": "10",
            "page": "2",
            "query": "청평리 161",
            "key": settings.vworld_api_key,
        }
        return httpx2.Response(200, text=_fixture("vworld_search_ok.json"))

    search_parcels("청평리 161", 2, client=_client(handler))


def test_ok_maps_total_and_lots():
    handler = _respond(200, _fixture("vworld_search_ok.json"))
    total, lots = search_parcels("청평리 161", 1, client=_client(handler))

    assert total == 29
    assert len(lots) == 10
    assert lots[0] == VworldLot("5111038022101610001", "강원특별자치도 춘천시 북산면 청평리 161-1")


def test_ok_with_no_items():
    body = {"response": {"status": "OK", "record": {"total": "0"}, "result": {"items": []}}}
    handler = _respond(200, json.dumps(body))

    assert search_parcels("청평리 161", 1, client=_client(handler)) == (0, [])


def test_not_found_is_empty():
    handler = _respond(200, _fixture("vworld_search_not_found.json"))

    assert search_parcels("청평리 9999", 1, client=_client(handler)) == (0, [])


def test_error_status_maps_to_code():
    body = {"response": {"status": "ERROR", "error": {"code": "INVALID_KEY", "text": "x"}}}

    details = _upstream_details(_respond(200, json.dumps(body)))

    assert details == {"source": "vworld", "upstream_code": "INVALID_KEY"}


def test_html_400_maps_to_upstream_error():
    handler = _respond(400, "<!DOCTYPE html><title>400 Bad Request</title>")

    assert _upstream_details(handler) == {"source": "vworld"}


@pytest.mark.parametrize("error", [None, "oops"])
def test_error_status_without_error_object(error):
    body = {"response": {"status": "ERROR", "error": error}}

    assert _upstream_details(_respond(200, json.dumps(body))) == {"source": "vworld"}


@pytest.mark.parametrize(
    "path, value", [("id", None), ("id", 41820), ("parcel", None), ("parcel", 161)]
)
def test_item_with_non_string_field_raises(path, value):
    body = json.loads(_fixture("vworld_search_ok.json"))
    item = body["response"]["result"]["items"][0]
    if path == "id":
        item["id"] = value
    else:
        item["address"]["parcel"] = value

    assert _upstream_details(_respond(200, json.dumps(body))) == {"source": "vworld"}


def test_item_without_id_raises():
    body = json.loads(_fixture("vworld_search_ok.json"))
    del body["response"]["result"]["items"][0]["id"]

    assert _upstream_details(_respond(200, json.dumps(body))) == {"source": "vworld"}


@pytest.mark.parametrize("error", [httpx2.ReadTimeout, httpx2.ConnectError])
def test_network_errors_map_to_upstream_error(error):
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise error("boom", request=request)

    assert _upstream_details(handler) == {"source": "vworld"}
