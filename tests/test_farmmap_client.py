from pathlib import Path

import httpx2
import pytest

from app.core.config import settings
from app.core.errors import AppError
from app.farm.infrastructure.integrations.farmmap import parcels_by_pnu

PNU = "4182032521101610003"
FIXTURE = Path(__file__).parent / "fixtures" / "farmmap_pnu_4182032521101610003.xml"
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
