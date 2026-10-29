from app.catalog.infrastructure.static_data import load


def auth(uid):
    return {"X-User-Id": str(uid)}


def test_crops_requires_authentication(client):
    r = client.get("/crops")

    assert (r.status_code, r.json()["error"]["code"]) == (401, "UNAUTHORIZED")


def test_pesticides_requires_authentication(client):
    r = client.get("/pesticides", params={"crop_id": 1})

    assert (r.status_code, r.json()["error"]["code"]) == (401, "UNAUTHORIZED")


def test_crops_shape(client, make_user):
    r = client.get("/crops", headers=auth(make_user("farmer")))

    assert r.status_code == 200
    assert r.json() == [
        {"id": 1, "name": "감자"},
        {"id": 2, "name": "배추"},
        {"id": 3, "name": "토마토"},
    ]


def test_pesticides_shape(client, make_user):
    r = client.get("/pesticides", params={"crop_id": 2}, headers=auth(make_user("farmer")))
    items = r.json()

    assert r.status_code == 200
    assert len(items) == 1008
    assert all(set(i) == {"id", "name", "item_name", "moa", "at_planting_only"} for i in items)
    assert all(isinstance(i["at_planting_only"], bool) for i in items)
    assert len({i["id"] for i in items}) == len(items)
    with_moa = [i["moa"] for i in items if i["moa"] is not None]
    assert with_moa and all(set(m) == {"label_kr", "system", "code"} for m in with_moa)
    assert any(i["moa"] is None for i in items)


def test_pest_filter_narrows_the_list(client, make_user):
    headers = auth(make_user("farmer"))
    all_items = client.get("/pesticides", params={"crop_id": 1}, headers=headers).json()
    narrowed = client.get("/pesticides", params={"crop_id": 1, "pest_id": 1}, headers=headers)

    assert narrowed.status_code == 200
    assert 0 < len(narrowed.json()) < len(all_items)


def test_unknown_crop_is_404(client, make_user):
    r = client.get("/pesticides", params={"crop_id": 99}, headers=auth(make_user("farmer")))

    assert (r.status_code, r.json()["error"]["code"]) == (404, "NOT_FOUND")


def test_unknown_pest_is_404(client, make_user):
    params = {"crop_id": 1, "pest_id": 999999}
    r = client.get("/pesticides", params=params, headers=auth(make_user("farmer")))

    assert (r.status_code, r.json()["error"]["code"]) == (404, "NOT_FOUND")


def test_pest_of_another_crop_is_404(client, make_user):
    other = next(p["pest_id"] for p in load("pest") if p["crop_id"] == 2)
    r = client.get(
        "/pesticides",
        params={"crop_id": 1, "pest_id": other},
        headers=auth(make_user("farmer")),
    )

    assert (r.status_code, r.json()["error"]["code"]) == (404, "NOT_FOUND")


def test_missing_or_bad_crop_id_is_422(client, make_user):
    headers = auth(make_user("farmer"))

    for params in ({}, {"crop_id": "abc"}):
        r = client.get("/pesticides", params=params, headers=headers)

        assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_ERROR")
