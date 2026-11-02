import pytest

from app.catalog.application import catalog_service
from app.catalog.domain.entities import LabelRead
from app.catalog.infrastructure.integrations import label_reader
from app.core.upstream import upstream_error

URL = "/ocr/pesticide-labels"
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
WEBP = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 64
MAX_BYTES = 5 * 1024 * 1024
DETAIL_KEYS = {"id", "name", "item_name", "moa", "company", "form", "ingredients", "kind"}


def auth(uid):
    return {"X-User-Id": str(uid)}


def post(client, headers, data, *, field="image", ctype="image/jpeg"):
    return client.post(URL, headers=headers, files={field: ("label", data, ctype)})


def fake_reader(monkeypatch, read):
    """읽는 척하는 가짜. 받은 media_type을 모아 돌려준다."""
    seen = []

    def reader(image, media_type):
        seen.append(media_type)
        return read

    monkeypatch.setattr(label_reader, "read_label", reader)
    return seen


def test_requires_authentication(client):
    r = client.post(URL)

    assert (r.status_code, r.json()["error"]["code"]) == (401, "UNAUTHORIZED")


def test_response_shape(client, make_user, monkeypatch):
    drug = catalog_service.all_pesticides()[0]
    fake_reader(monkeypatch, LabelRead(drug.name, drug.item_name, drug.company, "원문"))

    r = post(client, auth(make_user("farmer")), JPEG)

    body = r.json()
    assert r.status_code == 200
    assert set(body) == {"candidates", "read"}
    assert body["read"] == {
        "brand": drug.name,
        "product": drug.item_name,
        "company": drug.company,
        "text": "원문",
    }
    first = body["candidates"][0]
    assert set(first) == {"pesticide", "score", "matched"}
    assert set(first["pesticide"]) == DETAIL_KEYS
    assert (first["pesticide"]["id"], first["score"]) == (drug.id, 1.0)
    assert first["matched"] == ["brand", "product", "company"]


def test_candidate_id_works_in_a_judgment(client, make_user, make_field, make_zone, monkeypatch):
    uid = make_user("farmer")
    zone = make_zone(make_field(uid), uid)
    drug = catalog_service.all_pesticides()[0]
    fake_reader(monkeypatch, LabelRead(drug.name, drug.item_name, None, ""))

    scan = post(client, auth(uid), JPEG).json()
    judged = client.post(
        f"/zones/{zone}/judgments",
        json={"pesticide_id": scan["candidates"][0]["pesticide"]["id"]},
        headers=auth(uid),
    )

    assert judged.status_code == 201


def test_nothing_read_is_200_with_no_candidates(client, make_user, monkeypatch):
    fake_reader(monkeypatch, LabelRead(None, None, None, ""))

    r = post(client, auth(make_user("farmer")), JPEG)

    assert r.status_code == 200
    assert r.json() == {
        "candidates": [],
        "read": {"brand": None, "product": None, "company": None, "text": ""},
    }


BAD_UPLOADS = [
    pytest.param(lambda c, h: c.post(URL, headers=h), id="no-file"),
    pytest.param(lambda c, h: post(c, h, JPEG, field="file"), id="wrong-field-name"),
    pytest.param(lambda c, h: post(c, h, b""), id="empty"),
    pytest.param(lambda c, h: post(c, h, b"hello"), id="text-declared-as-jpeg"),
]


@pytest.mark.parametrize("send", BAD_UPLOADS)
def test_bad_uploads_are_422(client, make_user, monkeypatch, send):
    monkeypatch.setattr(label_reader, "read_label", lambda *a: pytest.fail("reader was called"))

    r = send(client, auth(make_user("farmer")))

    assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_ERROR")
    assert r.json()["error"]["details"]["errors"][0]["loc"] == ["body", "image"]
    assert "hello" not in r.text


def test_size_limit_is_exact(client, make_user, monkeypatch):
    fake_reader(monkeypatch, LabelRead(None, None, None, ""))
    headers = auth(make_user("farmer"))
    exact = JPEG + b"\x00" * (MAX_BYTES - len(JPEG))

    assert post(client, headers, exact).status_code == 200
    over = post(client, headers, exact + b"\x00")
    assert (over.status_code, over.json()["error"]["code"]) == (422, "VALIDATION_ERROR")
    assert over.json()["error"]["details"]["errors"][0]["loc"] == ["body", "image"]


@pytest.mark.parametrize(
    "data, expected",
    [(JPEG, "image/jpeg"), (PNG, "image/png"), (WEBP, "image/webp")],
    ids=["jpeg", "png", "webp"],
)
def test_signature_decides_the_media_type(client, make_user, monkeypatch, data, expected):
    seen = fake_reader(monkeypatch, LabelRead(None, None, None, ""))

    r = post(client, auth(make_user("farmer")), data, ctype="application/octet-stream")

    assert r.status_code == 200
    assert seen == [expected]


def test_upstream_failure_is_502_without_leaking(client, make_user, monkeypatch):
    def failing(image, media_type):
        raise upstream_error("anthropic", "m", "429", cause="RateLimitError")

    monkeypatch.setattr(label_reader, "read_label", failing)

    r = post(client, auth(make_user("farmer")), JPEG)

    assert (r.status_code, r.json()["error"]["code"]) == (502, "UPSTREAM_ERROR")
    assert r.json()["error"]["details"] == {"source": "anthropic", "upstream_code": "429"}
