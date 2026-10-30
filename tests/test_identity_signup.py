import pytest
from pydantic import ValidationError
from sqlalchemy import text

from app.identity.application import service
from app.identity.presentation.schemas import SignupIn
from tests.farm_support import install_fake_farmmap

VALID = {
    "username": "farmer_1",
    "password": "pw1234",
    "field_name": "앞밭",
    "parcel_farmmap_ids": ["1", "2"],
}


def body(**changes):
    return {**VALID, **changes}


def test_valid_body_is_accepted_and_the_field_name_is_stripped():
    parsed = SignupIn.model_validate(body(field_name="  앞밭  "))
    assert (parsed.username, parsed.password, parsed.field_name) == ("farmer_1", "pw1234", "앞밭")
    assert parsed.parcel_farmmap_ids == ["1", "2"]


def test_boundary_values_are_accepted():
    # 비밀번호는 자르지 않는다 (공백 4칸도 유효)
    SignupIn.model_validate(body(username="abc", password=" " * 4, field_name="f"))
    SignupIn.model_validate(
        body(
            username="a" * 30,
            password="x" * 72,
            field_name="f" * 30,
            parcel_farmmap_ids=[str(i) for i in range(1, 21)],
        )
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"username": "ab"},
        {"username": "a" * 31},
        {"username": "farmer\n"},
        {"username": "farm er"},
        {"username": "farmer-1"},
        {"username": "농부농부"},
        {"username": "１２３４"},
        {"password": "abc"},
        {"password": "x" * 73},
        {"field_name": ""},
        {"field_name": "   "},
        {"field_name": "f" * 31},
        {"parcel_farmmap_ids": []},
        {"parcel_farmmap_ids": [str(i) for i in range(1, 22)]},
        {"parcel_farmmap_ids": ["1", "1"]},
        {"parcel_farmmap_ids": [""]},
        {"parcel_farmmap_ids": ["12a"]},
        {"parcel_farmmap_ids": ["１２"]},
    ],
)
def test_invalid_bodies_are_rejected(changes):
    with pytest.raises(ValidationError):
        SignupIn.model_validate(body(**changes))


@pytest.mark.parametrize("missing", list(VALID))
def test_a_missing_key_is_rejected(missing):
    with pytest.raises(ValidationError):
        SignupIn.model_validate({k: v for k, v in VALID.items() if k != missing})


@pytest.fixture
def fake_farmmap(monkeypatch):
    return install_fake_farmmap(monkeypatch)


def signup(client, **changes):
    return client.post("/auth/signup", json=body(**changes))


def total_users(db):
    return db.scalar(text("SELECT count(*) FROM users"))


def test_signup_creates_the_user_and_the_first_field(client, fake_farmmap):
    response = signup(client)  # 인증 헤더 없이

    assert response.status_code == 201
    data = response.json()
    assert set(data) == {"id", "username", "field"}
    assert data["username"] == "farmer_1"
    field = data["field"]
    assert set(field) == {"id", "name", "area_m2", "geometry", "bbox", "zones"}
    assert (field["name"], field["area_m2"], field["zones"]) == ("앞밭", 200.0, [])
    fields = client.get("/fields", headers={"X-User-Id": str(data["id"])})
    assert fields.json() == [field]
    login = client.post("/auth/login", json={"username": "farmer_1", "password": "pw1234"})
    assert (login.status_code, login.json()) == (200, {"id": data["id"], "username": "farmer_1"})


def test_taken_username_is_409_before_any_farmmap_call(client, db, fake_farmmap):
    old = service.register_user(db, "farmer_1", "other_pw")
    before = total_users(db)

    response = signup(client)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "USERNAME_TAKEN"
    assert fake_farmmap[0] == []
    assert total_users(db) == before
    assert service.login(db, "farmer_1", "other_pw") == (old, "farmer_1")


def test_usernames_are_case_sensitive(client, fake_farmmap):
    assert signup(client, username="Farmer_1").status_code == 201
    assert signup(client, username="farmer_1").status_code == 201


def test_unknown_parcel_is_422_and_leaves_no_user(client, db, fake_farmmap):
    fake_farmmap[1].add("2")
    before = total_users(db)

    response = signup(client)

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    [item] = error["details"]["errors"]
    assert item["loc"] == ["body", "parcel_farmmap_ids", 1] and item["type"] == "not_found"
    assert total_users(db) == before


def test_farmmap_failure_is_502_leaves_no_user_and_the_name_is_free_again(
    client, db, fake_farmmap
):
    fake_farmmap[2].add("1")
    before = total_users(db)

    response = signup(client)

    assert response.status_code == 502
    assert response.json()["error"]["details"] == {"source": "farmmap"}
    assert total_users(db) == before
    fake_farmmap[2].clear()
    assert signup(client).status_code == 201


@pytest.mark.parametrize(
    "changes",
    [
        {"parcel_farmmap_ids": ["1", "1"]},
        {"username": "ab"},
        {"password": "abc"},
        {"field_name": " "},
    ],
)
def test_invalid_body_is_422_before_any_user_or_farmmap_call(client, db, fake_farmmap, changes):
    before = total_users(db)

    response = signup(client, **changes)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert fake_farmmap[0] == []
    assert total_users(db) == before
