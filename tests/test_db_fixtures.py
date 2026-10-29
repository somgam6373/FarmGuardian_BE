from sqlalchemy import text

PROBE = "rollback-probe"


def _count(db):
    return db.scalar(text("SELECT count(*) FROM users WHERE username = :n"), {"n": PROBE})


def test_a_inserts_probe_user(db, make_user):
    make_user(PROBE)

    assert _count(db) == 1


def test_b_probe_user_was_rolled_back(db):  # 정의 순서에 기대는 테스트: test_a 다음에 실행된다
    assert _count(db) == 0


def test_zone_is_linked_to_its_field_and_user(db, make_user, make_field, make_zone):
    uid = make_user("farmer")
    fid = make_field(uid)
    zid = make_zone(fid, uid)

    row = db.execute(text("SELECT field_id, user_id FROM zone WHERE id = :i"), {"i": zid}).one()

    assert tuple(row) == (fid, uid)
