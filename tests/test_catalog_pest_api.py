import pytest

CARD_KEYS = {
    "id",
    "name",
    "kind",
    "photo_url",
    "photo_source",
    "description",
    "occurrence",
    "occurrence_source",
    "vectors",
}


def auth(uid):
    return {"X-User-Id": str(uid)}


def candidates(client, headers, crop_id, part):
    params = {"crop_id": crop_id, "part": part}
    response = client.get("/pests/candidates", params=params, headers=headers)
    return {c["id"]: c for c in response.json()}


@pytest.mark.parametrize(
    "path,params",
    [
        ("/crops/1/symptom-parts", {}),
        ("/pests/candidates", {"crop_id": 1, "part": "잎"}),
        ("/pests", {"crop_id": 1}),
    ],
)
def test_requires_authentication(client, path, params):
    r = client.get(path, params=params)

    assert (r.status_code, r.json()["error"]["code"]) == (401, "UNAUTHORIZED")


def test_symptom_parts_shape(client, make_user):
    r = client.get("/crops/3/symptom-parts", headers=auth(make_user("farmer")))

    assert (r.status_code, r.json()) == (200, ["뿌리", "잎", "줄기", "벌레", "열매"])


def test_candidates_shape(client, make_user):
    params = {"crop_id": 2, "part": "벌레"}
    r = client.get("/pests/candidates", params=params, headers=auth(make_user("farmer")))
    cards = r.json()

    assert r.status_code == 200
    assert len(cards) == 27
    assert all(set(c) == CARD_KEYS for c in cards)
    assert [c["name"] for c in cards] == sorted(c["name"] for c in cards)


def test_pests_list_and_filter(client, make_user):
    headers = auth(make_user("farmer"))
    everything = client.get("/pests", params={"crop_id": 2}, headers=headers).json()
    filtered = client.get("/pests", params={"crop_id": 2, "q": "나방"}, headers=headers).json()

    assert len(everything) == 43
    assert 0 < len(filtered) < len(everything)
    assert all("나방" in c["name"] for c in filtered)


def test_card_values_and_nulls(client, make_user):
    headers = auth(make_user("farmer"))
    potato = candidates(client, headers, 1, "덩이")
    with_data = potato[8]  # 역병 (감자)
    no_season = potato[1]  # 가루더뎅이병 (감자, 발생 시기 없음)
    no_photo = candidates(client, headers, 2, "잎")[24]  # 그루썩음병 (배추, 사진 없음)

    assert with_data["kind"] == "병"
    assert with_data["occurrence"] == "6~7월 — 대관령 · 고랭지, 씨감자 · 예보"
    assert with_data["occurrence_source"] == "PDF 경보"
    assert (no_season["occurrence"], no_season["occurrence_source"]) == (None, None)
    assert (no_photo["photo_url"], no_photo["photo_source"]) == (None, None)
    assert no_season["vectors"] == [] and no_photo["vectors"] == []


def test_vectors_shape(client, make_user):
    headers = auth(make_user("farmer"))
    cards = {}
    for part in ("뿌리", "잎", "줄기", "벌레", "열매"):
        cards |= candidates(client, headers, 3, part)
    virus = next(c for c in cards.values() if c["vectors"])

    assert all(set(v) == {"id", "name", "guide", "source"} for v in virus["vectors"])


@pytest.mark.parametrize(
    "path,params",
    [
        ("/crops/99/symptom-parts", {}),
        ("/pests/candidates", {"crop_id": 99, "part": "잎"}),
        ("/pests", {"crop_id": 99}),
    ],
)
def test_unknown_crop_is_404(client, make_user, path, params):
    r = client.get(path, params=params, headers=auth(make_user("farmer")))

    assert (r.status_code, r.json()["error"]["code"]) == (404, "NOT_FOUND")


def test_part_outside_the_crops_list_is_422_with_its_location(client, make_user):
    params = {"crop_id": 3, "part": "덩이"}
    r = client.get("/pests/candidates", params=params, headers=auth(make_user("farmer")))
    error = r.json()["error"]

    assert (r.status_code, error["code"]) == (422, "VALIDATION_ERROR")
    assert error["details"]["errors"][0]["loc"] == ["query", "part"]
    assert "덩이" not in str(error)


@pytest.mark.parametrize(
    "path,params",
    [
        ("/pests/candidates", {"crop_id": 1}),
        ("/pests/candidates", {"part": "잎"}),
        ("/pests", {}),
    ],
)
def test_missing_query_values_are_422(client, make_user, path, params):
    r = client.get(path, params=params, headers=auth(make_user("farmer")))

    assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_ERROR")
