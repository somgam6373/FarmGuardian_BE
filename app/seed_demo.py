import argparse
from datetime import date, timedelta
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.catalog.application import catalog_service
from app.core.auth import DEMO_USERNAME
from app.core.db import SessionLocal
from app.core.time import today_kst
from app.farm.application import field_service
from app.identity.domain.password import hash_password

POTATO, CABBAGE, TOMATO = 1, 2, 3
DIAMONDBACK_MOTH, LATE_BLIGHT, GRAY_MOLD = 48, 8, 75

# 시연 사례를 만드는 약. tests/test_seed_demo.py가 판정 결과를 확인한다
OK_DRUG = "베네비아"  # 앞 구역: 네 가지 모두 통과
SAME_GROUP_DRUG = "박빙"  # 가운데 구역: 같은 계통 연속 (로건과 같은 3a)
USED_UP_DRUG = "라이몬"  # 뒤 구역: 최대 2회를 다 씀
TOMATO_DRUG = "미기와"  # 토마토: 심기 전, 누락 확인 전
INVENTORY = (OK_DRUG, "델리게이트", "엑사이도", SAME_GROUP_DRUG)

# 평창 대관령 근처의 네모난 밭 (EPSG:5179 미터 좌표). 팜맵 없이 다시 만들 수 있게 코드에 둔다
_CABBAGE_FIELD = (
    "MULTIPOLYGON(((993780 1970300,993880 1970306,993876 1970366,993776 1970360,993780 1970300)))"
)
_TEST_FIELD = (
    "MULTIPOLYGON(((993900 1970300,993980 1970304,993977 1970374,993897 1970370,993900 1970300)))"
)

# (밭 이름, 주소, 도형, 비율, 구역들)
# 구역 = (이름, 작물, 심은 지 며칠, 수확까지 며칠, 누락 없음, [(약, 병해충, 며칠 전에 뿌림)])
_FIELDS = (
    (
        "대관령 배추밭",
        "강원특별자치도 평창군 대관령면 (체험용)",
        _CABBAGE_FIELD,
        [5, 3, 2],
        (
            (
                "앞 구역",
                CABBAGE,
                60,
                30,
                True,
                [("검투사", DIAMONDBACK_MOTH, 40), ("델리게이트", DIAMONDBACK_MOTH, 20)],
            ),
            (
                "가운데 구역",
                CABBAGE,
                60,
                None,
                True,
                [("로건", DIAMONDBACK_MOTH, 30), ("로건", DIAMONDBACK_MOTH, 12)],
            ),
            (
                "뒤 구역",
                CABBAGE,
                60,
                None,
                True,
                [(USED_UP_DRUG, DIAMONDBACK_MOTH, 35), (USED_UP_DRUG, DIAMONDBACK_MOTH, 15)],
            ),
        ),
    ),
    (
        "횡계 시험밭",
        "강원특별자치도 평창군 대관령면 횡계리 (체험용)",
        _TEST_FIELD,
        [1, 1, 1],
        (
            ("감자 구역", POTATO, 30, None, True, [("텔루스", LATE_BLIGHT, 10)]),
            ("토마토 새 구역", TOMATO, None, None, False, []),
            ("토마토 확인 전", TOMATO, 20, None, False, [("칸투스", GRAY_MOLD, 5)]),
        ),
    ),
)


def ensure_dev_user(db: Session) -> int:
    # '!'는 잠금 해시라 어떤 비밀번호와도 맞지 않는다. dev는 X-User-Id 헤더로만 쓴다
    # (BE-17 로그인은 이 값을 '불일치'로 처리해야 한다). 커밋은 호출한 쪽이 한다.
    db.execute(
        text(
            "INSERT INTO users (username, password_hash) VALUES ('dev', '!') "
            "ON CONFLICT (username) DO NOTHING"
        )
    )
    return db.scalar(text("SELECT id FROM users WHERE username = 'dev'"))


def _drug_id(name: str) -> int:
    return next(d.id for d in catalog_service.all_pesticides() if d.name == name)


def _add_zones(db: Session, user_id: int, field_id: int, ratios, zones, today: date) -> None:
    def ago(days: int | None) -> date | None:
        return None if days is None else today - timedelta(days=days)

    created = field_service.create_zones(
        db,
        field_id,
        user_id,
        "crosswise",
        ratios,
        [{"name": z[0], "crop_id": z[1], "planted_at": ago(z[2])} for z in zones],
        today,
    )
    for zone, (_, _, _, harvest_in, confirmed, sprays) in zip(created, zones):
        db.execute(
            text("UPDATE zone SET harvest_at = :harvest, history_confirmed = :ok WHERE id = :id"),
            {
                "id": zone["id"],
                "ok": confirmed,
                "harvest": None if harvest_in is None else today + timedelta(days=harvest_in),
            },
        )
        for drug, pest_id, days_ago in sprays:
            db.execute(
                text(
                    "INSERT INTO spray_log "
                    "(zone_id, pesticide_id, sprayed_on, source, request_id, pest_id) "
                    "VALUES (:zone, :drug, :day, 'manual', :rid, :pest)"
                ),
                {
                    "zone": zone["id"],
                    "drug": _drug_id(drug),
                    "day": ago(days_ago),
                    "rid": uuid4(),
                    "pest": pest_id,
                },
            )


def seed_demo_account(db: Session) -> int:
    """체험 계정을 처음 상태로 만든다. 다시 실행해도 id는 그대로다. 커밋은 호출한 쪽이 한다."""
    today = today_kst()
    user_id = db.scalar(
        text(
            "INSERT INTO users (username, password_hash, onboarded_at) "
            "VALUES (:name, :hash, now()) "
            "ON CONFLICT (username) DO UPDATE "
            "SET password_hash = EXCLUDED.password_hash, onboarded_at = now() "
            "RETURNING id"
        ),
        {"name": DEMO_USERNAME, "hash": hash_password(DEMO_USERNAME)},
    )
    # 구역, 살포 기록, 판정은 밭을 따라 함께 지워진다
    db.execute(text("DELETE FROM field WHERE user_id = :u"), {"u": user_id})
    db.execute(text("DELETE FROM inventory WHERE user_id = :u"), {"u": user_id})
    for name, address, wkt, ratios, zones in _FIELDS:
        field_id = db.scalar(
            text(
                "INSERT INTO field (user_id, name, address, geom) "
                "VALUES (:u, :name, :address, ST_GeomFromText(:wkt, 5179)) RETURNING id"
            ),
            {"u": user_id, "name": name, "address": address, "wkt": wkt},
        )
        _add_zones(db, user_id, field_id, ratios, zones, today)
    for drug in INVENTORY:
        db.execute(
            text("INSERT INTO inventory (user_id, pesticide_id) VALUES (:u, :drug)"),
            {"u": user_id, "drug": _drug_id(drug)},
        )
    return user_id


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="개발용·시연용 시드 데이터를 넣는다")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--dev-user",
        action="store_true",
        help="밭·구역 없이 사용자 dev만 만든다 (프론트가 이 id를 X-User-Id로 쓴다)",
    )
    group.add_argument(
        "--demo",
        action="store_true",
        help="체험 계정 test1을 처음 상태로 만든다. 그 계정의 기존 데이터는 지워진다",
    )
    args = parser.parse_args(argv)
    with SessionLocal() as db:
        if args.demo:
            print(f"demo user id: {seed_demo_account(db)}")
        else:
            print(f"dev user id: {ensure_dev_user(db)}")
        db.commit()


if __name__ == "__main__":
    main()
