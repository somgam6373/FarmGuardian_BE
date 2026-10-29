from datetime import date

import pytest
from sqlalchemy import text

from app.core.errors import AppError
from app.farm.application import zone_reader


def test_reads_crop_planting_date_and_confirmation(db, make_user, make_field, make_zone):
    uid = make_user("farmer")
    zone = make_zone(make_field(uid), uid)
    first_crop = db.scalar(text("SELECT min(id) FROM crop"))

    context = zone_reader.get_zone_context(db, zone)
    assert (context.crop_id, context.planted_at, context.history_confirmed) == (
        first_crop,
        None,
        False,
    )

    db.execute(
        text(
            "UPDATE zone SET crop_id = 3, planted_at = '2026-04-01', "
            "history_confirmed = true WHERE id = :id"
        ),
        {"id": zone},
    )
    context = zone_reader.get_zone_context(db, zone)

    assert (context.crop_id, context.planted_at, context.history_confirmed) == (
        3,
        date(2026, 4, 1),
        True,
    )


def test_unknown_zone_is_404(db):
    with pytest.raises(AppError) as info:
        zone_reader.get_zone_context(db, 999999)

    assert (info.value.status, info.value.code) == (404, "NOT_FOUND")


def test_lists_the_users_zones_by_id_with_their_confirmation(db, make_user, make_field, make_zone):
    uid = make_user("farmer")
    field = make_field(uid)
    first, second = make_zone(field, uid), make_zone(field, uid)
    db.execute(text("UPDATE zone SET history_confirmed = true WHERE id = :id"), {"id": second})

    assert zone_reader.list_user_zones(db, uid) == [
        zone_reader.ZoneState(first, False),
        zone_reader.ZoneState(second, True),
    ]


def test_listing_excludes_other_users_zones(db, make_user, make_field, make_zone):
    mine, other = make_user("mine"), make_user("other")
    make_zone(make_field(other), other)

    assert zone_reader.list_user_zones(db, mine) == []
