import pytest
from pydantic import ValidationError

from app.identity.presentation.schemas import SignupIn

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
