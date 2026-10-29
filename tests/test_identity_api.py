import uuid

import pytest
from sqlalchemy import text

from app.identity.application import service

SQUARE = "ST_GeomFromText('MULTIPOLYGON(((0 0,10 0,10 10,0 10,0 0)))', 5179)"


def auth(uid):
    return {"X-User-Id": str(uid)}


def login(client, username="farmer_1", password="pw1234"):
    return client.post("/auth/login", json={"username": username, "password": password})


@pytest.fixture
def user(db):
    return service.register_user(db, "farmer_1", "pw1234")


def confirm(db, zone_id, value=True):
    db.execute(
        text("UPDATE zone SET history_confirmed = :v WHERE id = :id"), {"v": value, "id": zone_id}
    )


def test_login_returns_exactly_the_id_and_username(client, user):
    r = login(client)

    assert (r.status_code, r.json()) == (200, {"id": user, "username": "farmer_1"})


def test_login_ignores_a_sent_user_header(client, user, make_user):
    other = make_user("other")
    r = client.post(
        "/auth/login", json={"username": "farmer_1", "password": "pw1234"}, headers=auth(other)
    )

    assert r.json()["id"] == user


def test_every_failure_gets_the_same_401_body(client, user, db, make_user):
    db.execute(text("INSERT INTO users (username, password_hash) VALUES ('dev', '!')"))
    make_user("fixture_user")  # hash 'x'
    attempts = [
        ("farmer_1", "wrong"),
        ("nobody", "pw1234"),
        ("dev", "!"),
        ("fixture_user", "x"),
    ]
    responses = [login(client, name, password) for name, password in attempts]

    assert {r.status_code for r in responses} == {401}
    assert {r.json()["error"]["code"] for r in responses} == {"UNAUTHORIZED"}
    assert len({str(r.json()) for r in responses}) == 1


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"username": "a"},
        {"password": "pw"},
        {"username": "", "password": "pw"},
        {"username": "a", "password": ""},
        {"username": "a" * 101, "password": "pw"},
        {"username": "a", "password": "p" * 101},
    ],
    ids=[
        "empty",
        "no-password",
        "no-username",
        "blank-name",
        "blank-password",
        "long-name",
        "long-password",
    ],
)
def test_malformed_login_bodies_are_422(client, body):
    r = client.post("/auth/login", json=body)

    assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_ERROR")


def test_values_of_exactly_100_characters_are_accepted_and_simply_wrong(client):
    r = login(client, "a" * 100, "p" * 100)

    assert (r.status_code, r.json()["error"]["code"]) == (401, "UNAUTHORIZED")


@pytest.mark.parametrize("headers", [{}, {"X-User-Id": "999999"}], ids=["no-header", "unknown-id"])
def test_me_requires_a_known_user(client, headers):
    r = client.get("/me", headers=headers)

    assert (r.status_code, r.json()["error"]["code"]) == (401, "UNAUTHORIZED")


def test_me_shape_and_onboarding_state(client, user):
    r = client.get("/me", headers=auth(user))

    assert (r.status_code, r.json()) == (
        200,
        {"id": user, "username": "farmer_1", "onboarded": False},
    )


def test_onboarding_without_zones_is_422_with_the_details(client, user):
    r = client.post("/me/onboarding", headers=auth(user))
    error = r.json()["error"]

    assert (r.status_code, error["code"]) == (422, "ONBOARDING_INCOMPLETE")
    assert error["details"] == {"zone_count": 0, "unconfirmed_zone_ids": []}


def test_onboarding_names_the_unconfirmed_zones(client, db, user, make_field, make_zone):
    field = make_field(user)
    first, second = make_zone(field, user), make_zone(field, user)
    confirm(db, first)
    r = client.post("/me/onboarding", headers=auth(user))

    assert r.status_code == 422
    assert r.json()["error"]["details"] == {"zone_count": 2, "unconfirmed_zone_ids": [second]}


def test_onboarding_completes_and_shows_in_me(client, db, user, make_field, make_zone):
    confirm(db, make_zone(make_field(user), user))
    r = client.post("/me/onboarding", headers=auth(user))

    assert (r.status_code, r.json()) == (200, {"id": user, "onboarded": True})
    assert client.get("/me", headers=auth(user)).json()["onboarded"] is True


def test_onboarding_is_idempotent_and_survives_an_unconfirmed_zone(
    client, db, user, make_field, make_zone
):
    zone = make_zone(make_field(user), user)
    confirm(db, zone)
    first = client.post("/me/onboarding", headers=auth(user))
    stamp = db.scalar(text("SELECT onboarded_at FROM users WHERE id = :id"), {"id": user})
    confirm(db, zone, False)
    again = client.post("/me/onboarding", headers=auth(user))

    assert (first.status_code, again.status_code) == (200, 200)
    assert again.json() == {"id": user, "onboarded": True}
    assert db.scalar(text("SELECT onboarded_at FROM users WHERE id = :id"), {"id": user}) == stamp


def test_onboarding_requires_authentication(client):
    r = client.post("/me/onboarding")

    assert (r.status_code, r.json()["error"]["code"]) == (401, "UNAUTHORIZED")


def test_withdrawal_is_204_removes_the_user_and_the_header_stops_working(
    client, db, user, make_user, make_field, make_zone
):
    other = make_user("other")
    for owner in (user, other):
        field = make_field(owner)
        zone = make_zone(field, owner)
        db.execute(
            text(
                "INSERT INTO field_parcel (field_id, user_id, farmmap_id, pnu, geom) "
                f"VALUES (:f, :u, :fm, '1234567890123456789', {SQUARE})"
            ),
            {"f": field, "u": owner, "fm": f"fm-{owner}"},
        )
        db.execute(
            text(
                "INSERT INTO spray_log (zone_id, pesticide_id, sprayed_on, source, request_id) "
                "VALUES (:z, 1, '2026-01-01', 'manual', :r)"
            ),
            {"z": zone, "r": uuid.uuid4()},
        )
        db.execute(
            text(
                "INSERT INTO judgment (zone_id, pesticide_id, apply_date, verdict, result) "
                "VALUES (:z, 1, '2026-01-01', 'OK', '{}'::jsonb)"
            ),
            {"z": zone},
        )
    r = client.delete("/me", headers=auth(user))

    assert (r.status_code, r.content) == (204, b"")
    for table in ("users", "field", "field_parcel", "zone", "spray_log", "judgment"):
        assert db.scalar(text(f"SELECT count(*) FROM {table}")) == 1, table
    assert db.scalar(text("SELECT id FROM users")) == other
    assert client.get("/me", headers=auth(user)).status_code == 401
    assert client.delete("/me", headers=auth(user)).status_code == 401


def test_withdrawal_requires_authentication(client):
    r = client.delete("/me")

    assert (r.status_code, r.json()["error"]["code"]) == (401, "UNAUTHORIZED")


def post_raw(client, body):
    return client.post(
        "/auth/login", content=body.encode(), headers={"Content-Type": "application/json"}
    )


@pytest.mark.parametrize(
    "body",
    [
        r'{"username": "a\u0000b", "password": "pw1234"}',
        r'{"username": "farmer_1", "password": "pw\u00001234"}',
    ],
    ids=["nul-name", "nul-password"],
)
def test_a_nul_character_is_a_plain_401(client, user, body):
    r = post_raw(client, body)
    wrong = login(client, "farmer_1", "wrong")

    assert (r.status_code, r.json()) == (401, wrong.json())


@pytest.mark.parametrize(
    "body",
    [
        r'{"username": "\ud800", "password": "pw1234"}',
        r'{"username": "farmer_1", "password": "\ud800"}',
    ],
    ids=["surrogate-name", "surrogate-password"],
)
def test_an_unpaired_surrogate_is_a_validation_error_not_a_server_error(client, user, body):
    r = post_raw(client, body)

    assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_ERROR")
