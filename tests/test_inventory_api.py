import pytest
from sqlalchemy import text

from app.catalog.application import catalog_service

IDS = sorted(drug.id for drug in catalog_service.all_pesticides())
DRUG, SMALL, LARGE = IDS[len(IDS) // 2], IDS[0], IDS[-1]


def auth(uid):
    return {"X-User-Id": str(uid)}


def stored(db, uid):
    return db.scalar(text("SELECT count(*) FROM inventory WHERE user_id = :u"), {"u": uid})


@pytest.mark.parametrize(
    "method, path", [("post", "/inventory"), ("get", "/inventory"), ("delete", "/inventory/1")]
)
def test_requires_authentication(client, method, path):
    r = client.request(method, path, json={} if method == "post" else None)

    assert (r.status_code, r.json()["error"]["code"]) == (401, "UNAUTHORIZED")


def test_post_is_201_then_200_and_stores_one_row(client, db, make_user):
    uid = make_user("farmer")

    first = client.post("/inventory", json={"drug_id": DRUG}, headers=auth(uid))
    second = client.post("/inventory", json={"drug_id": DRUG}, headers=auth(uid))

    assert (first.status_code, first.json()) == (201, {"drug_id": DRUG})
    assert (second.status_code, second.json()) == (200, {"drug_id": DRUG})
    assert stored(db, uid) == 1


def test_get_lists_ids_oldest_first(client, make_user):
    uid = make_user("farmer")
    empty = client.get("/inventory", headers=auth(uid))
    for drug_id in (LARGE, SMALL):  # 담은 순서가 id 순서와 다르다
        client.post("/inventory", json={"drug_id": drug_id}, headers=auth(uid))

    listed = client.get("/inventory", headers=auth(uid))

    assert (empty.status_code, empty.json()) == (200, [])
    assert (listed.status_code, listed.json()) == (200, [LARGE, SMALL])


@pytest.mark.parametrize(
    "body",
    [{}, {"drug_id": None}, {"drug_id": "abc"}, {"drug_id": 1.5}, {"drug_id": 0},
     {"drug_id": -5}, {"drug_id": 2**40},
     {"drug_id": True},  # JSON true를 약제 1번으로 받으면 안 된다
     {"drug_id": str(DRUG)}],  # 숫자 문자열도 정수가 아니다 (명세: drug_id는 int)
)
def test_post_rejects_bad_bodies_and_unknown_drugs(client, db, make_user, body):
    uid = make_user("farmer")

    r = client.post("/inventory", json=body, headers=auth(uid))

    assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_ERROR")
    assert r.json()["error"]["details"]["errors"][0]["loc"] == ["body", "drug_id"]
    assert stored(db, uid) == 0


def test_delete_is_204_then_404(client, make_user):
    uid = make_user("farmer")
    client.post("/inventory", json={"drug_id": DRUG}, headers=auth(uid))

    first = client.delete(f"/inventory/{DRUG}", headers=auth(uid))
    again = client.delete(f"/inventory/{DRUG}", headers=auth(uid))

    assert (first.status_code, first.content) == (204, b"")
    assert (again.status_code, again.json()["error"]["code"]) == (404, "NOT_FOUND")
    assert client.get("/inventory", headers=auth(uid)).json() == []


@pytest.mark.parametrize("drug_id", [0, -1, 2**40])
def test_delete_unknown_and_huge_ids_are_404(client, make_user, drug_id):
    r = client.delete(f"/inventory/{drug_id}", headers=auth(make_user("farmer")))

    assert (r.status_code, r.json()["error"]["code"]) == (404, "NOT_FOUND")
    # 없는 경로의 404("Not Found")와 구분한다: 이 라우트가 직접 낸 404여야 한다
    assert r.json()["error"]["message"] == "찾을 수 없습니다"


def test_delete_with_a_non_integer_id_is_422(client, make_user):
    r = client.delete("/inventory/abc", headers=auth(make_user("farmer")))

    assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_ERROR")


def test_inventories_are_per_user(client, make_user):
    owner, other = make_user("owner"), make_user("other")
    client.post("/inventory", json={"drug_id": DRUG}, headers=auth(owner))

    assert client.get("/inventory", headers=auth(other)).json() == []
    assert client.delete(f"/inventory/{DRUG}", headers=auth(other)).status_code == 404
    assert client.get("/inventory", headers=auth(owner)).json() == [DRUG]


def test_withdrawal_removes_the_inventory(client, db, make_user):
    uid = make_user("farmer")
    client.post("/inventory", json={"drug_id": DRUG}, headers=auth(uid))
    assert stored(db, uid) == 1

    r = client.delete("/me", headers=auth(uid))

    assert r.status_code == 204
    assert stored(db, uid) == 0
