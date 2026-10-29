import uuid

import pytest
from sqlalchemy import text

from app.core.time import today_kst
from tests.judgment_scenarios import (
    PLANTED,
    TODAY,
    counting_selection,
    pest_with_alternatives,
    pests_with_drugs,
    pool,
    unregistered_drug,
)

RESPONSE_KEYS = {"judgment_id", "apply_date", "result", "alternatives", "show_extension_office"}
RESULT_KEYS = {"pesticide_id", "moa", "verdict", "checks", "notices", "data_asof"}
CHECK_KEYS = {"key", "status", "message", "facts", "evidence"}
ALT_KEYS = {"id", "name", "item_name", "moa"}
NOTICE = "병해충을 지정하면 대안을 볼 수 있습니다"
PEST = pests_with_drugs(1)[0]
DRUG = pool(1, PEST)[0]


def auth(uid):
    return {"X-User-Id": str(uid)}


@pytest.fixture
def farm(make_user, make_field, make_zone):
    uid = make_user("farmer")
    return uid, make_zone(make_field(uid), uid)


def confirm(db, zone):
    db.execute(
        text("UPDATE zone SET planted_at = :p, history_confirmed = true WHERE id = :id"),
        {"p": PLANTED, "id": zone},
    )


def judge(client, uid, zone, **body):
    return client.post(f"/zones/{zone}/judgments", json=body, headers=auth(uid))


def stored(db, zone):
    return db.execute(
        text(
            "SELECT id, pest_id, pesticide_id, apply_date, verdict, result "
            "FROM judgment WHERE zone_id = :z ORDER BY id"
        ),
        {"z": zone},
    ).all()


def test_requires_authentication(client):
    r = client.post("/zones/1/judgments", json={})

    assert (r.status_code, r.json()["error"]["code"]) == (401, "UNAUTHORIZED")


def test_foreign_and_unknown_zones_are_404(client, make_user, make_field, make_zone, farm):
    uid, _ = farm
    other = make_user("other")
    foreign = make_zone(make_field(other), other)
    for zone in (foreign, 999999):
        r = client.post(f"/zones/{zone}/judgments", json={}, headers=auth(uid))  # 404 beats 422

        assert (r.status_code, r.json()["error"]["code"]) == (404, "NOT_FOUND")


def test_unknown_pesticide_is_404_and_stores_nothing(client, db, farm):
    uid, zone = farm
    r = judge(client, uid, zone, pesticide_id=999999)

    assert (r.status_code, r.json()["error"]["code"]) == (404, "NOT_FOUND")
    assert stored(db, zone) == []


@pytest.mark.parametrize("pest_id", [999999, pests_with_drugs(2)[0]], ids=["unknown", "other-crop"])
def test_unknown_pest_or_pest_of_another_crop_is_404_and_stores_nothing(client, db, farm, pest_id):
    uid, zone = farm
    r = judge(client, uid, zone, pesticide_id=DRUG.id, pest_id=pest_id)

    assert (r.status_code, r.json()["error"]["code"]) == (404, "NOT_FOUND")
    assert stored(db, zone) == []


def test_apply_date_after_2100_is_422_but_the_last_day_of_2100_is_accepted(client, db, farm):
    uid, zone = farm
    r = judge(client, uid, zone, pesticide_id=DRUG.id, apply_date="2101-01-01")
    error = r.json()["error"]

    assert (r.status_code, error["code"]) == (422, "VALIDATION_ERROR")
    assert error["details"]["errors"][0]["loc"] == ["body", "apply_date"]
    assert "2101" not in str(error)
    assert stored(db, zone) == []
    accepted = judge(client, uid, zone, pesticide_id=DRUG.id, apply_date="2100-12-31")
    assert (accepted.status_code, accepted.json()["apply_date"]) == (201, "2100-12-31")


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"pesticide_id": "x"},
        {"pesticide_id": 1, "pest_id": "x"},
        {"pesticide_id": 1, "apply_date": "nope"},
    ],
    ids=["empty", "pesticide-type", "pest-type", "date-type"],
)
def test_malformed_bodies_are_422_and_store_nothing(client, db, farm, body):
    uid, zone = farm
    r = judge(client, uid, zone, **body)

    assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_ERROR")
    assert stored(db, zone) == []


def test_response_has_exactly_the_spec_shape(client, db, farm):
    uid, zone = farm
    confirm(db, zone)
    r = judge(client, uid, zone, pesticide_id=DRUG.id, pest_id=PEST, apply_date=TODAY.isoformat())
    body = r.json()
    result = body["result"]

    assert r.status_code == 201 and set(body) == RESPONSE_KEYS
    assert set(result) == RESULT_KEYS and result["pesticide_id"] == DRUG.id
    assert [c["key"] for c in result["checks"]] == ["registration", "timing", "count", "moa"]
    assert all(set(c) == CHECK_KEYS for c in result["checks"])
    assert all(set(c["evidence"]) == {"source_text", "data_asof"} for c in result["checks"])
    assert result["verdict"] in {"OK", "CAUTION", "BLOCKED", "NEEDS_CHECK"}
    assert result["data_asof"] == "2026-10-05"
    assert all(set(a) == ALT_KEYS for a in body["alternatives"])
    assert isinstance(body["show_extension_office"], bool)


def test_the_judgment_is_stored(client, db, farm):
    uid, zone = farm
    body = judge(
        client, uid, zone, pesticide_id=DRUG.id, pest_id=PEST, apply_date="2026-10-29"
    ).json()
    (row,) = stored(db, zone)

    assert row.id == body["judgment_id"]
    assert (row.pest_id, row.pesticide_id, row.apply_date.isoformat()) == (
        PEST,
        DRUG.id,
        "2026-10-29",
    )
    assert row.verdict == body["result"]["verdict"]
    assert row.result == body["result"]


def test_unspecified_pest_is_stored_as_null(client, db, farm):
    uid, zone = farm
    judge(client, uid, zone, pesticide_id=DRUG.id)

    assert [row.pest_id for row in stored(db, zone)] == [None]


def test_every_call_stores_its_own_row(client, db, farm):
    uid, zone = farm
    first = judge(client, uid, zone, pesticide_id=DRUG.id).json()
    second = judge(client, uid, zone, pesticide_id=DRUG.id).json()

    assert first["judgment_id"] != second["judgment_id"]
    assert [row.id for row in stored(db, zone)] == [first["judgment_id"], second["judgment_id"]]


def test_apply_date_defaults_to_today_kst_and_an_explicit_one_is_echoed(client, db, farm):
    uid, zone = farm
    default = judge(client, uid, zone, pesticide_id=DRUG.id).json()
    explicit = judge(client, uid, zone, pesticide_id=DRUG.id, apply_date="2026-01-15").json()

    assert default["apply_date"] == today_kst().isoformat()
    assert explicit["apply_date"] == "2026-01-15"
    assert [row.apply_date.isoformat() for row in stored(db, zone)] == [
        today_kst().isoformat(),
        "2026-01-15",
    ]


def test_stored_spray_is_counted_whatever_the_apply_date(client, db, farm):
    uid, zone = farm
    confirm(db, zone)
    pest_id, drug = counting_selection()

    def used(apply_date):
        body = judge(
            client, uid, zone, pesticide_id=drug.id, pest_id=pest_id, apply_date=apply_date
        ).json()
        return body["result"]["checks"][2]["facts"]["used"]

    assert used("2026-04-15") == 0
    sprayed = client.post(
        f"/zones/{zone}/sprays",
        json={
            "pesticide_id": drug.id,
            "source": "manual",
            "request_id": str(uuid.uuid4()),
            "sprayed_on": "2026-05-01",
        },
        headers=auth(uid),
    )
    assert sprayed.status_code == 201
    assert used("2026-04-15") == 1 and used("2026-10-29") == 1


def test_judgment_creates_no_spray_record(client, db, farm):
    uid, zone = farm
    judge(client, uid, zone, pesticide_id=DRUG.id, pest_id=PEST)

    assert db.scalar(text("SELECT count(*) FROM spray_log WHERE zone_id = :z"), {"z": zone}) == 0


def test_alternatives_and_the_office_flag(client, db, farm):
    uid, zone = farm
    chosen, pest = unregistered_drug(), pest_with_alternatives()
    request = {"pesticide_id": chosen.id, "pest_id": pest, "apply_date": TODAY.isoformat()}

    unconfirmed = judge(client, uid, zone, **request).json()  # nothing can be OK yet
    assert unconfirmed["result"]["verdict"] == "BLOCKED"
    assert (unconfirmed["alternatives"], unconfirmed["show_extension_office"]) == ([], True)

    confirm(db, zone)
    confirmed = judge(client, uid, zone, **request).json()
    keys = [(a["moa"]["label_kr"], a["item_name"], a["name"]) for a in confirmed["alternatives"]]
    ids = {a["id"] for a in confirmed["alternatives"]}

    assert confirmed["alternatives"] and confirmed["show_extension_office"] is False
    assert keys == sorted(keys)
    assert ids <= {d.id for d in pool(1, pest)} and chosen.id not in ids


def test_unspecified_pest_notice(client, farm):
    uid, zone = farm
    body = judge(client, uid, zone, pesticide_id=unregistered_drug().id).json()

    assert body["result"]["notices"] == [NOTICE]
    assert (body["alternatives"], body["show_extension_office"]) == ([], False)


def test_unregistered_drug_is_blocked_not_an_error(client, farm):
    uid, zone = farm
    r = judge(client, uid, zone, pesticide_id=unregistered_drug().id, pest_id=PEST)
    first_check = r.json()["result"]["checks"][0]

    assert r.status_code == 201 and r.json()["result"]["verdict"] == "BLOCKED"
    assert (first_check["status"], first_check["facts"]) == ("BLOCKED", {"crop_registered": False})
