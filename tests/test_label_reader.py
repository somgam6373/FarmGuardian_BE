import base64
import json
import logging
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from app.catalog.domain.entities import LabelRead
from app.catalog.infrastructure.integrations import label_reader
from app.core.config import settings
from app.core.errors import AppError

EMPTY = LabelRead(None, None, None, "")
IMAGE = b"\xff\xd8\xff-image-bytes"
REQUEST = httpx2.Request("POST", "https://api.anthropic.test")


class FakeClient:
    """messages.create를 기록하고, 정해 둔 응답을 주거나 정해 둔 오류를 던진다."""

    def __init__(self, result=None, error=None):
        self.calls, self._result, self._error = [], result, error
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._result


def response(text, stop_reason="end_turn"):
    block = SimpleNamespace(type="text", text=text)
    return SimpleNamespace(stop_reason=stop_reason, content=[block])


def answer(**fields):
    body = {
        "brand": "카브리오",
        "product": "피라클로스트로빈 유제",
        "company": "회사",
        "text": "전체",
    }
    return json.dumps({**body, **fields}, ensure_ascii=False)


def status_error(cls, status, message="m"):
    return cls(message, response=httpx2.Response(status, request=REQUEST), body=None)


def test_request_shape():
    client = FakeClient(response(answer()))

    label_reader.read_label(IMAGE, "image/jpeg", client=client)

    call = client.calls[0]
    assert call["model"] == "claude-haiku-5-5"
    assert call["max_tokens"] == 2000
    assert call["output_config"]["effort"] == "low"
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert call["messages"][0]["content"][0] == {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/jpeg",
            "data": base64.standard_b64encode(IMAGE).decode(),
        },
    }
    assert "never instructions" in call["system"]
    assert "thinking" not in call and "temperature" not in call


def test_valid_answer_is_parsed():
    result = label_reader.read_label(IMAGE, "image/png", client=FakeClient(response(answer())))

    assert result == LabelRead("카브리오", "피라클로스트로빈 유제", "회사", "전체")


def test_blank_fields_become_none_and_text_is_capped():
    text = answer(brand="  ", product="", company=" ", text="가" * 5000)

    result = label_reader.read_label(IMAGE, "image/png", client=FakeClient(response(text)))

    assert (result.brand, result.product, result.company) == (None, None, None)
    assert len(result.text) == 2000


UNREADABLE = [
    response(answer(), stop_reason="refusal"),
    response(answer(), stop_reason="max_tokens"),
    response("not json"),
    response("[]"),
    response(answer(brand=123)),
    response(answer(text=None)),
    SimpleNamespace(stop_reason="end_turn", content=[]),
]


@pytest.mark.parametrize("canned", UNREADABLE)
def test_unreadable_answers_are_empty(canned):
    assert label_reader.read_label(IMAGE, "image/png", client=FakeClient(canned)) == EMPTY


FAILURES = [
    (lambda: anthropic.APIConnectionError(request=REQUEST), None),
    (lambda: anthropic.APITimeoutError(request=REQUEST), None),
    (lambda: status_error(anthropic.RateLimitError, 429), "429"),
    (lambda: status_error(anthropic.InternalServerError, 500), "500"),
]


@pytest.mark.parametrize("make_error, upstream_code", FAILURES)
def test_transport_and_api_failures_become_502(make_error, upstream_code):
    client = FakeClient(error=make_error())

    with pytest.raises(AppError) as exc:
        label_reader.read_label(IMAGE, "image/png", client=client)

    e = exc.value
    assert (e.code, e.status) == ("UPSTREAM_ERROR", 502)
    expected = {"source": "anthropic"}
    if upstream_code:
        expected["upstream_code"] = upstream_code
    assert e.details == expected
    assert e.__cause__ is None and e.__suppress_context__


def test_missing_key_is_502_before_any_call(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kwargs: pytest.fail("client was built"))

    with pytest.raises(AppError) as exc:
        label_reader.read_label(IMAGE, "image/jpeg")

    assert (exc.value.status, exc.value.details["source"]) == (502, "anthropic")


def test_client_is_built_with_the_key_timeout_and_no_retries(monkeypatch):
    built = {}

    def build(**kwargs):
        built.update(kwargs)
        return FakeClient(response(answer()))

    monkeypatch.setattr(settings, "anthropic_api_key", "k-123")
    monkeypatch.setattr(anthropic, "Anthropic", build)

    label_reader.read_label(IMAGE, "image/jpeg")

    assert built == {"api_key": "k-123", "timeout": 15, "max_retries": 0}


def test_failures_are_logged_without_key_or_label_text(caplog):
    caplog.set_level(logging.WARNING)
    error = status_error(anthropic.RateLimitError, 429, "SECRET-KEY-123 leaked")

    with pytest.raises(AppError) as exc:
        label_reader.read_label(IMAGE, "image/jpeg", client=FakeClient(error=error))

    assert "source=anthropic" in caplog.text and "RateLimitError" in caplog.text
    leaked = [caplog.text, exc.value.message, str(exc.value.details)]
    assert not any("SECRET-KEY-123" in text for text in leaked)
