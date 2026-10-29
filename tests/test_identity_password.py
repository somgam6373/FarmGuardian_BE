import hashlib

import pytest

from app.identity.domain.password import hash_password, verify_password


@pytest.mark.parametrize("password", ["pw1234", "비밀번호1234", "a" * 72, "😀🌱", " spaced pass "])
def test_round_trip(password):
    assert verify_password(password, hash_password(password)) is True


def test_a_wrong_password_is_rejected():
    stored = hash_password("correct")

    assert verify_password("Correct", stored) is False
    assert verify_password("correct ", stored) is False
    assert verify_password("", stored) is False


def test_each_hash_has_its_own_salt_and_never_contains_the_password():
    first, second = hash_password("same-password"), hash_password("same-password")

    assert first != second
    assert "same-password" not in first


def test_a_fixed_salt_makes_the_hash_reproducible():
    salt = b"0123456789abcdef"

    assert hash_password("pw", salt) == hash_password("pw", salt)


def test_the_stored_string_carries_its_parameters():
    scheme, n, r, p, salt, digest = hash_password("pw").split("$")

    assert (scheme, int(n), int(r), int(p)) == ("scrypt", 2**14, 8, 1)
    assert len(bytes.fromhex(salt)) == 16 and len(bytes.fromhex(digest)) == 32


def test_a_hash_made_with_other_parameters_still_verifies():
    salt = b"s" * 16
    digest = hashlib.scrypt(b"pw", salt=salt, n=2**10, r=4, p=2, dklen=32)
    stored = f"scrypt$1024$4$2${salt.hex()}${digest.hex()}"

    assert verify_password("pw", stored) is True
    assert verify_password("pw!", stored) is False


@pytest.mark.parametrize(
    "stored",
    [
        "!",
        "x",
        "",
        "scrypt",
        "scrypt$16384$8$1$aa",
        "scrypt$16384$8$1$zz$zz",
        "scrypt$abc$8$1$00$00",
        "scrypt$16384$8$1$$",
        "bcrypt$16384$8$1$00$00",
        "scrypt$1073741824$8$1$00$00",
        "scrypt$3$8$1$00$00",
        "scrypt$16384$8$1$00$00$extra",
        "scrypt$16384$8$1$00$00",
    ],
)
def test_malformed_or_locked_values_never_match_and_never_raise(stored):
    assert verify_password("anything", stored) is False
