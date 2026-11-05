import pytest
from sqlalchemy import text

from app.seed_demo import (
    OK_DRUG,
    SAME_GROUP_DRUG,
    TOMATO_DRUG,
    USED_UP_DRUG,
    ensure_dev_user,
    seed_demo_account,
)


def test_creates_the_locked_dev_user(db):
    uid = ensure_dev_user(db)

    row = db.execute(
        text("SELECT username, password_hash FROM users WHERE id = :i"), {"i": uid}
    ).one()

    assert tuple(row) == ("dev", "!")


def test_is_idempotent(db):
    first, second = ensure_dev_user(db), ensure_dev_user(db)

    assert first == second
    assert db.scalar(text("SELECT count(*) FROM users WHERE username = 'dev'")) == 1


def auth(uid):
    return {"X-User-Id": str(uid)}


def checks(client, uid, zone_id, pest_id, drug):
    items = client.get(
        f"/zones/{zone_id}/judgments/preview", params={"pest_id": pest_id}, headers=auth(uid)
    ).json()
    item = next(i for i in items if i["pesticide"]["name"] == drug)
    return {c["key"]: c["status"] for c in item["result"]["checks"]}


@pytest.fixture
def demo(db):
    uid = seed_demo_account(db)
    zones = {
        row.name: row.id
        for row in db.execute(text("SELECT id, name FROM zone WHERE user_id = :u"), {"u": uid})
    }
    return uid, zones


def test_demo_account_logs_in_with_the_easy_password_and_is_onboarded(client, demo):
    uid, _ = demo
    r = client.post("/auth/login", json={"username": "test1", "password": "test1"})

    assert r.status_code == 200 and r.json()["id"] == uid
    assert client.get("/me", headers=auth(uid)).json()["onboarded"] is True


def test_demo_account_has_two_fields_with_six_zones_and_inventory(client, demo):
    uid, _ = demo
    fields = client.get("/fields", headers=auth(uid)).json()

    assert [len(f["zones"]) for f in fields] == [3, 3]
    assert client.get("/inventory", headers=auth(uid)).json()


def test_each_zone_shows_its_demo_case(client, demo):
    uid, z = demo

    assert set(checks(client, uid, z["앞 구역"], 48, OK_DRUG).values()) == {"OK"}
    assert checks(client, uid, z["가운데 구역"], 48, SAME_GROUP_DRUG)["moa"] == "CAUTION"
    assert checks(client, uid, z["뒤 구역"], 48, USED_UP_DRUG)["count"] == "BLOCKED"
    planting = checks(client, uid, z["감자 구역"], 1, "엑사이도")
    assert planting["timing"] == "NEEDS_CHECK"
    assert checks(client, uid, z["토마토 새 구역"], 75, TOMATO_DRUG)["count"] == "NEEDS_CHECK"
    assert checks(client, uid, z["토마토 확인 전"], 75, TOMATO_DRUG)["moa"] == "NEEDS_CHECK"


def test_seeding_again_restores_the_data_and_keeps_the_user_id(client, db, demo):
    uid, z = demo
    client.patch(f"/zones/{z['앞 구역']}", json={"name": "낙서"}, headers=auth(uid))
    db.execute(text("DELETE FROM inventory WHERE user_id = :u"), {"u": uid})

    assert seed_demo_account(db) == uid

    names = db.scalars(text("SELECT name FROM zone WHERE user_id = :u"), {"u": uid}).all()
    assert "앞 구역" in names and "낙서" not in names
    assert client.get("/inventory", headers=auth(uid)).json()


def test_demo_account_cannot_withdraw_or_delete_a_field(client, demo):
    uid, _ = demo
    field_id = client.get("/fields", headers=auth(uid)).json()[0]["id"]

    for method, url in (("DELETE", "/me"), ("DELETE", f"/fields/{field_id}")):
        r = client.request(method, url, headers=auth(uid))
        assert r.status_code == 403
        assert r.json()["error"]["code"] == "DEMO_ACCOUNT"
    assert len(client.get("/fields", headers=auth(uid)).json()) == 2


def test_other_users_can_still_withdraw(client, make_user):
    assert client.delete("/me", headers=auth(make_user("farmer"))).status_code == 204
