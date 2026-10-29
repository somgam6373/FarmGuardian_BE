from pathlib import Path

import httpx2
import pytest

from app.core.config import settings
from app.core.errors import AppError
from app.farm.infrastructure.integrations.farmmap import parcel_by_id, parcels_by_pnu

PNU = "4182032521101610003"
FIXTURE = Path(__file__).parent / "fixtures" / "farmmap_pnu_4182032521101610003.xml"
ID = "418203252100637"
ID_FIXTURE = Path(__file__).parent / "fixtures" / "farmmap_id_418203252100637.xml"
NO_DATA = "<response><header><resultCode>3</resultCode></header></response>"
GATEWAY_ERROR = (
    "<OpenAPI_ServiceResponse><cmmMsgHeader><errMsg>SERVICE ERROR</errMsg>"
    "<returnReasonCode>30</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>"
)


def _client(handler) -> httpx2.Client:
    return httpx2.Client(transport=httpx2.MockTransport(handler))


def _upstream_details(handler) -> dict:
    with pytest.raises(AppError) as exc:
        parcels_by_pnu(PNU, client=_client(handler))
    assert exc.value.status == 502
    return exc.value.details


def test_sends_key_type_and_pnu():
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path.endswith("/getFarmmapService/getPnuBasedFarmmapInfo")
        assert request.url.params["serviceKey"] == settings.farmmap_api_key
        assert request.url.params["type"] == "xml"
        assert request.url.params["pnuCode"] == PNU
        return httpx2.Response(200, text=FIXTURE.read_text(encoding="utf-8"))

    assert len(parcels_by_pnu(PNU, client=_client(handler))) == 2


def test_gateway_403_maps_to_reason_code():
    details = _upstream_details(lambda r: httpx2.Response(403, text=GATEWAY_ERROR))
    assert details == {"source": "farmmap", "upstream_code": "30"}


def test_html_500_maps_to_upstream_error():
    details = _upstream_details(lambda r: httpx2.Response(500, text="<html>error"))
    assert details == {"source": "farmmap"}


@pytest.mark.parametrize("error", [httpx2.ReadTimeout, httpx2.ConnectError])
def test_network_errors_map_to_upstream_error(error):
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise error("boom", request=request)

    assert _upstream_details(handler) == {"source": "farmmap"}


def _respond(status: int, text: str):
    return lambda request: httpx2.Response(status, text=text)


def test_by_id_sends_key_type_and_id():
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path.endswith("/getFarmmapService/getIdBasedFarmmapInfo")
        assert request.url.params["serviceKey"] == settings.farmmap_api_key
        assert request.url.params["type"] == "xml"
        assert request.url.params["id"] == ID
        return httpx2.Response(200, text=ID_FIXTURE.read_text(encoding="utf-8"))

    assert parcel_by_id(ID, client=_client(handler)) is not None


def test_by_id_returns_the_parcel():
    handler = _respond(200, ID_FIXTURE.read_text(encoding="utf-8"))

    parcel = parcel_by_id(ID, client=_client(handler))

    assert (parcel.farmmap_id, parcel.lnm, parcel.land_use) == (ID, "161-3전", "밭")


def test_by_id_no_data_is_none():
    assert parcel_by_id(ID, client=_client(_respond(200, NO_DATA))) is None


def test_by_id_empty_id_is_none():
    assert parcel_by_id("", client=_client(_respond(200, NO_DATA))) is None


def test_by_id_other_parcel_only_is_none():
    # 팜맵이 요청한 번호가 아닌 필지만 돌려주면 다른 필지 모양을 쓰지 않는다
    handler = _respond(200, FIXTURE.read_text(encoding="utf-8"))

    assert parcel_by_id("999999999999999", client=_client(handler)) is None


def test_by_id_picks_requested_among_many():
    handler = _respond(200, FIXTURE.read_text(encoding="utf-8"))

    parcel = parcel_by_id("418203252100655", client=_client(handler))

    assert parcel.lnm == "160-7답"


def test_by_id_gateway_403_maps_to_reason_code():
    with pytest.raises(AppError) as exc:
        parcel_by_id(ID, client=_client(_respond(403, GATEWAY_ERROR)))
    assert exc.value.details == {"source": "farmmap", "upstream_code": "30"}


def test_by_id_timeout_maps_to_upstream_error():
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("boom", request=request)

    with pytest.raises(AppError) as exc:
        parcel_by_id(ID, client=_client(handler))
    assert exc.value.status == 502
    assert exc.value.details == {"source": "farmmap"}
