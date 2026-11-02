import uuid
from datetime import timedelta

import pytest
from sqlalchemy import text

from app.core.time import today_kst
from tests.judgment_scenarios import PLANTED, counting_selection

PEST, DRUG = counting_selection()


def auth(uid):
    return {"X-User-Id": str(uid)}


@pytest.fixture
def farm(db, make_user, make_field, make_zone):
    uid = make_user("farmer")
    zone = make_zone(make_field(uid), uid)
    db.execute(
        text("UPDATE zone SET planted_at = :p, history_confirmed = true WHERE id = :id"),
        {"p": PLANTED, "id": zone},
    )
    return uid, zone


def spray(client, uid, zone, days_ago=1):
    body = {
        "pesticide_id": DRUG.id,
        "pest_id": PEST,
        "sprayed_on": (today_kst() - timedelta(days=days_ago)).isoformat(),
        "source": "manual",
        "request_id": str(uuid.uuid4()),
    }
    r = client.post(f"/zones/{zone}/sprays", json=body, headers=auth(uid))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def cancel(client, uid, zone, sid):
    assert client.delete(f"/zones/{zone}/sprays/{sid}", headers=auth(uid)).status_code == 204


def restore(client, uid, zone, sid):
    r = client.post(f"/zones/{zone}/sprays/{sid}/restore", headers=auth(uid))
    assert r.status_code == 200, r.text


def used(client, uid, zone):
    body = {"pesticide_id": DRUG.id, "pest_id": PEST}
    r = client.post(f"/zones/{zone}/judgments", json=body, headers=auth(uid))
    assert r.status_code == 201, r.text
    count = next(c for c in r.json()["result"]["checks"] if c["key"] == "count")
    return count["facts"]["used"]


def test_cancelled_spray_is_not_counted_by_the_count_check(client, farm):
    uid, zone = farm
    sid = spray(client, uid, zone)
    assert used(client, uid, zone) == 1

    cancel(client, uid, zone, sid)
    assert used(client, uid, zone) == 0

    restore(client, uid, zone, sid)
    assert used(client, uid, zone) == 1


def test_cancelled_spray_is_not_in_the_rotation_summary(client, farm):
    uid, zone = farm
    sid = spray(client, uid, zone)

    def total():
        r = client.get(f"/zones/{zone}", headers=auth(uid))
        return r.json()["rotation"]["total"]

    before = total()
    assert before == 1
    cancel(client, uid, zone, sid)
    assert total() == 0
    restore(client, uid, zone, sid)
    assert total() == before


def test_last_spray_on_the_fields_list_skips_cancelled_rows(client, farm):
    uid, zone = farm
    older = spray(client, uid, zone, days_ago=5)
    newer = spray(client, uid, zone, days_ago=1)

    def last_spray():
        fields = client.get("/fields", headers=auth(uid)).json()
        summary = next(z for f in fields for z in f["zones"] if z["id"] == zone)
        return summary["last_spray"]

    assert last_spray()["sprayed_on"] == (today_kst() - timedelta(days=1)).isoformat()
    cancel(client, uid, zone, newer)
    assert last_spray()["sprayed_on"] == (today_kst() - timedelta(days=5)).isoformat()
    cancel(client, uid, zone, older)
    assert last_spray() is None
