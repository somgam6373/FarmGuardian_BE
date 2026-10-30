from datetime import date, timedelta

import pytest
from sqlalchemy import event, text

from app.core.errors import AppError
from app.farm.application import zone_service

TODAY = date(2026, 10, 30)
MAY = date(2026, 5, 1)


@pytest.fixture
def zone(db, make_user, make_field, make_zone):
    def make(planted_at=MAY, confirmed=True):
        uid = make_user(f"u{planted_at}{confirmed}")
        zone_id = make_zone(make_field(uid), uid)
        db.execute(
            text("UPDATE zone SET planted_at = :p, history_confirmed = :c WHERE id = :id"),
            {"p": planted_at, "c": confirmed, "id": zone_id},
        )
        return zone_id

    return make


def state(z):
    return z["crop"]["id"], z["planted_at"], z["history_confirmed"]


@pytest.mark.parametrize(
    "changes, expected",
    [
        ({"crop_id": 2}, (2, None, False)),
        ({"crop_id": 2, "planted_at": date(2026, 9, 1)}, (2, date(2026, 9, 1), False)),
        ({"crop_id": 2, "history_confirmed": True}, (2, None, True)),
        ({"crop_id": 1}, (1, MAY, True)),
        ({"planted_at": date(2026, 6, 1)}, (1, date(2026, 6, 1), False)),
        ({"planted_at": date(2026, 6, 1), "history_confirmed": True}, (1, date(2026, 6, 1), True)),
        ({"planted_at": MAY}, (1, MAY, True)),
        ({"planted_at": None}, (1, None, False)),
        ({"history_confirmed": False}, (1, MAY, False)),
        ({"planted_at": TODAY}, (1, TODAY, False)),
        ({}, (1, MAY, True)),
    ],
)
def test_update_rules(db, zone, changes, expected):
    assert state(zone_service.update_zone(db, zone(), changes, TODAY)) == expected


@pytest.mark.parametrize("changes", [{"crop_id": 2}, {"planted_at": None}])
def test_empty_date_keeps_confirmation(db, zone, changes):
    updated = zone_service.update_zone(db, zone(planted_at=None), changes, TODAY)
    assert updated["planted_at"] is None and updated["history_confirmed"] is True


def test_rename_only(db, zone):
    updated = zone_service.update_zone(db, zone(), {"name": "앞쪽"}, TODAY)
    assert updated["name"] == "앞쪽" and state(updated) == (1, MAY, True)


def test_future_date_is_422(db, zone):
    zone_id = zone()
    with pytest.raises(AppError) as error:
        zone_service.update_zone(db, zone_id, {"planted_at": TODAY + timedelta(days=1)}, TODAY)
    [err] = error.value.details["errors"]
    assert err["loc"] == ["body", "planted_at"]
    assert state(zone_service.get_zones(db, [zone_id])[0]) == (1, MAY, True)


def test_unknown_crop_and_future_date_together(db, zone):
    changes = {"crop_id": 999, "planted_at": date(2027, 1, 1)}
    with pytest.raises(AppError) as error:
        zone_service.update_zone(db, zone(), changes, TODAY)
    assert [e["loc"] for e in error.value.details["errors"]] == [
        ["body", "crop_id"],
        ["body", "planted_at"],
    ]


def test_update_locks_zone_row_before_reading(db, zone):
    # 동시 수정에서 한쪽 변경이 사라지지 않게 읽을 때 행을 잠근다
    zone_id = zone()
    statements = []
    connection = db.connection()

    def record(conn, cursor, statement, *args):
        statements.append(statement)

    event.listen(connection, "before_cursor_execute", record)
    zone_service.update_zone(db, zone_id, {"name": "x"}, TODAY)
    event.remove(connection, "before_cursor_execute", record)
    read = next(s for s in statements if s.lstrip().startswith("SELECT name, crop_id"))
    assert "FOR UPDATE" in read
