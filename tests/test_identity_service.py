import uuid

import pytest
from sqlalchemy import text

from app.core.errors import AppError
from app.identity.application import service
from app.identity.domain.password import verify_password

SQUARE = "ST_GeomFromText('MULTIPOLYGON(((0 0,10 0,10 10,0 10,0 0)))', 5179)"
TABLES = ("users", "field", "field_parcel", "zone", "spray_log", "judgment")


def stored_hash(db, user_id):
    return db.scalar(text("SELECT password_hash FROM users WHERE id = :id"), {"id": user_id})


def onboarded_at(db, user_id):
    return db.scalar(text("SELECT onboarded_at FROM users WHERE id = :id"), {"id": user_id})


def confirm(db, zone_id, value=True):
    db.execute(
        text("UPDATE zone SET history_confirmed = :v WHERE id = :id"), {"v": value, "id": zone_id}
    )


def give_data(db, user_id, make_field, make_zone):
    """One row in every table that belongs to a user; returns the zone id."""
    field = make_field(user_id)
    zone = make_zone(field, user_id)
    db.execute(
        text(
            "INSERT INTO field_parcel (field_id, user_id, farmmap_id, pnu, geom) "
            f"VALUES (:f, :u, :fm, '1234567890123456789', {SQUARE})"
        ),
        {"f": field, "u": user_id, "fm": f"fm-{user_id}"},
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
    return zone


def totals(db):
    return {t: db.scalar(text(f"SELECT count(*) FROM {t}")) for t in TABLES}


def test_register_user_stores_a_verifiable_hash_and_returns_the_id(db):
    user_id = service.register_user(db, "farmer_1", "pw1234")

    assert isinstance(user_id, int)
    assert verify_password("pw1234", stored_hash(db, user_id)) is True
    assert "pw1234" not in stored_hash(db, user_id)


def test_register_user_with_a_taken_name_returns_none_and_changes_nothing(db):
    first = service.register_user(db, "farmer_1", "pw1234")

    assert service.register_user(db, "farmer_1", "other-password") is None
    assert db.scalar(text("SELECT count(*) FROM users WHERE username = 'farmer_1'")) == 1
    assert verify_password("pw1234", stored_hash(db, first)) is True


def test_usernames_are_case_sensitive(db):
    assert service.register_user(db, "Farmer", "pw1234") is not None
    assert service.register_user(db, "farmer", "pw1234") is not None


def test_register_user_does_not_commit(db):
    service.register_user(db, "farmer_1", "pw1234")
    db.rollback()

    assert db.scalar(text("SELECT count(*) FROM users WHERE username = 'farmer_1'")) == 0


def test_login_returns_the_id_and_username(db):
    user_id = service.register_user(db, "farmer_1", "pw1234")

    assert service.login(db, "farmer_1", "pw1234") == (user_id, "farmer_1")


@pytest.mark.parametrize(
    "username,password",
    [("farmer_1", "wrong"), ("nobody", "pw1234"), ("farmer_1", ""), ("Farmer_1", "pw1234")],
    ids=["wrong-password", "unknown-name", "empty-password", "other-case"],
)
def test_every_login_failure_is_none(db, username, password):
    service.register_user(db, "farmer_1", "pw1234")

    assert service.login(db, username, password) is None


@pytest.mark.parametrize("locked", ["!", "x", ""], ids=["dev-lock", "fixture-x", "empty"])
def test_a_user_with_a_locked_or_malformed_hash_cannot_log_in(db, locked):
    db.execute(
        text("INSERT INTO users (username, password_hash) VALUES ('locked', :h)"), {"h": locked}
    )

    for password in ("!", "x", "", "pw1234", locked):
        assert service.login(db, "locked", password) is None


def test_an_unknown_name_still_runs_one_verification(db, monkeypatch):
    calls = []
    real = service.verify_password

    def spy(password, stored):
        calls.append(stored)
        return real(password, stored)

    monkeypatch.setattr(service, "verify_password", spy)

    assert service.login(db, "nobody", "pw1234") is None
    assert len(calls) == 1 and calls[0].startswith("scrypt$")


def test_get_me_reports_the_name_and_onboarding_state(db):
    user_id = service.register_user(db, "farmer_1", "pw1234")

    assert service.get_me(db, user_id) == service.Me(user_id, "farmer_1", False)


def test_get_me_of_a_missing_user_is_unauthorized(db):
    with pytest.raises(AppError) as info:
        service.get_me(db, 999999)

    assert (info.value.status, info.value.code) == (401, "UNAUTHORIZED")


def test_onboarding_without_zones_is_incomplete(db, make_user):
    uid = make_user("farmer")
    with pytest.raises(AppError) as info:
        service.complete_onboarding(db, uid)

    assert (info.value.status, info.value.code) == (422, "ONBOARDING_INCOMPLETE")
    assert info.value.details == {"zone_count": 0, "unconfirmed_zone_ids": []}
    assert onboarded_at(db, uid) is None


def test_onboarding_lists_the_unconfirmed_zones_in_order(db, make_user, make_field, make_zone):
    uid = make_user("farmer")
    field = make_field(uid)
    first, second, third = (make_zone(field, uid) for _ in range(3))
    confirm(db, second)
    with pytest.raises(AppError) as info:
        service.complete_onboarding(db, uid)

    assert info.value.details == {"zone_count": 3, "unconfirmed_zone_ids": [first, third]}
    assert onboarded_at(db, uid) is None


def test_onboarding_completes_when_every_zone_is_confirmed(db, make_user, make_field, make_zone):
    uid = make_user("farmer")
    field = make_field(uid)
    for _ in range(2):
        confirm(db, make_zone(field, uid))
    service.complete_onboarding(db, uid)

    assert onboarded_at(db, uid) is not None


def test_a_second_onboarding_keeps_the_first_timestamp(db, make_user, make_field, make_zone):
    uid = make_user("farmer")
    confirm(db, make_zone(make_field(uid), uid))
    service.complete_onboarding(db, uid)
    first = onboarded_at(db, uid)
    service.complete_onboarding(db, uid)

    assert onboarded_at(db, uid) == first


def test_a_finished_onboarding_is_not_undone_by_an_unconfirmed_zone(
    db, make_user, make_field, make_zone
):
    uid = make_user("farmer")
    zone = make_zone(make_field(uid), uid)
    confirm(db, zone)
    service.complete_onboarding(db, uid)
    confirm(db, zone, False)
    service.complete_onboarding(db, uid)

    assert onboarded_at(db, uid) is not None


def test_other_users_zones_do_not_count(db, make_user, make_field, make_zone):
    mine, other = make_user("mine"), make_user("other")
    confirm(db, make_zone(make_field(other), other))
    with pytest.raises(AppError) as info:
        service.complete_onboarding(db, mine)

    assert info.value.details == {"zone_count": 0, "unconfirmed_zone_ids": []}


def test_withdraw_removes_everything_of_the_user_and_only_that(
    db, make_user, make_field, make_zone
):
    gone, kept = make_user("gone"), make_user("kept")
    give_data(db, gone, make_field, make_zone)
    kept_zone = give_data(db, kept, make_field, make_zone)
    assert totals(db) == dict.fromkeys(TABLES, 2)
    service.withdraw(db, gone)

    assert totals(db) == dict.fromkeys(TABLES, 1)
    assert db.scalar(text("SELECT user_id FROM zone")) == kept
    assert db.scalar(text("SELECT zone_id FROM spray_log")) == kept_zone
    assert db.scalar(text("SELECT id FROM users")) == kept


def test_withdrawing_a_missing_user_is_not_an_error(db):
    service.withdraw(db, 999999)
