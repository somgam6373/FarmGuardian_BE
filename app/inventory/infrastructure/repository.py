from sqlalchemy import text
from sqlalchemy.orm import Session


def add(db: Session, user_id: int, pesticide_id: int) -> bool:
    """창고에 담는다. 이미 있으면 저장하지 않고 False. 커밋은 호출하는 쪽이 한다."""
    row = db.execute(
        text(
            "INSERT INTO inventory (user_id, pesticide_id) VALUES (:uid, :pid) "
            "ON CONFLICT DO NOTHING RETURNING pesticide_id"
        ),
        {"uid": user_id, "pid": pesticide_id},
    ).one_or_none()
    return row is not None


def remove(db: Session, user_id: int, pesticide_id: int) -> bool:
    """창고에서 뺀다. 없었으면 False. 커밋은 호출하는 쪽이 한다."""
    row = db.execute(
        text(
            "DELETE FROM inventory WHERE user_id = :uid AND pesticide_id = :pid "
            "RETURNING pesticide_id"
        ),
        {"uid": user_id, "pid": pesticide_id},
    ).one_or_none()
    return row is not None


def list_ids(db: Session, user_id: int) -> list[int]:
    """담은 순서(오래된 것 먼저)의 약제 id."""
    rows = db.scalars(
        text(
            "SELECT pesticide_id FROM inventory WHERE user_id = :uid "
            "ORDER BY created_at, pesticide_id"
        ),
        {"uid": user_id},
    )
    return list(rows)
