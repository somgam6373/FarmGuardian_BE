import logging

import httpx2
import pytest

from app.core import upstream
from app.core.errors import AppError

URL = "https://example.test/p"


def _client(handler) -> httpx2.Client:
    return httpx2.Client(transport=httpx2.MockTransport(handler))


def _raising(error):
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise error("boom", request=request)

    return handler


def test_get_returns_the_response_and_passes_the_params():
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path == "/p"
        assert dict(request.url.params) == {"a": "1", "b": "2"}
        return httpx2.Response(200, text="ok")

    response = upstream.get("x", "m", URL, {"a": "1", "b": "2"}, client=_client(handler))

    assert response.text == "ok"


@pytest.mark.parametrize("status", [403, 500])
def test_error_statuses_are_returned_not_raised(status):
    client = _client(lambda request: httpx2.Response(status, text="body"))

    response = upstream.get("x", "m", URL, {}, client=client)

    assert (response.status_code, response.text) == (status, "body")


@pytest.mark.parametrize("error", [httpx2.ReadTimeout, httpx2.ConnectError])
def test_transport_failures_become_502(error):
    with pytest.raises(AppError) as exc:
        upstream.get("x", "m", URL, {}, client=_client(_raising(error)))

    e = exc.value
    assert (e.code, e.status, e.message, e.details) == ("UPSTREAM_ERROR", 502, "m", {"source": "x"})


def test_upstream_error_details():
    assert upstream.upstream_error("x", "m", "30").details == {"source": "x", "upstream_code": "30"}
    assert upstream.upstream_error("x", "m").details == {"source": "x"}


def test_a_passed_client_stays_open_and_the_default_client_is_closed(monkeypatch):
    mine = _client(lambda request: httpx2.Response(200, text="ok"))
    upstream.get("x", "m", URL, {}, client=mine)
    assert mine.is_closed is False

    made = []

    def make(handler):
        client = _client(handler)
        made.append(client)
        return client

    monkeypatch.setattr(upstream, "new_client", lambda: make(lambda r: httpx2.Response(200)))
    upstream.get("x", "m", URL, {})
    monkeypatch.setattr(upstream, "new_client", lambda: make(_raising(httpx2.ConnectError)))
    with pytest.raises(AppError):
        upstream.get("x", "m", URL, {})

    assert [client.is_closed for client in made] == [True, True]


def test_new_client_uses_a_five_second_timeout():
    assert upstream.TIMEOUT_SECONDS == 5
    with upstream.new_client() as client:
        assert client.timeout == httpx2.Timeout(5)


def test_failures_are_logged_without_the_key(caplog):
    caplog.set_level(logging.WARNING)
    client = _client(_raising(httpx2.ReadTimeout))

    with pytest.raises(AppError):
        upstream.get("x", "m", URL, {"key": "SECRET-KEY-123"}, client=client)
    upstream.upstream_error("x", "m", "30")

    assert "source=x" in caplog.text and "ReadTimeout" in caplog.text
    assert "upstream_code=30" in caplog.text
    assert "SECRET-KEY-123" not in caplog.text and "example.test" not in caplog.text


def test_httpx2_request_logging_stays_off():
    assert logging.getLogger("httpx2").getEffectiveLevel() >= logging.WARNING
