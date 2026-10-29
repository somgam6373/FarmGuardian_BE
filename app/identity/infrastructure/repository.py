from sqlalchemy import text
from sqlalchemy.orm import Session


def insert_user(db: Session, username: str, password_hash: str) -> int | None:
    """아이디가 이미 있으면 저장하지 않고 None. 커밋은 호출하는 쪽이 한다."""
    return db.scalar(
        text(
            "INSERT INTO users (username, password_hash) VALUES (:name, :hash) "
            "ON CONFLICT (username) DO NOTHING RETURNING id"
        ),
        {"name": username, "hash": password_hash},
    )


def find_by_username(db: Session, username: str) -> tuple[int, str] | None:
    """(id, 비밀번호 해시)."""
    row = db.execute(
        text("SELECT id, password_hash FROM users WHERE username = :name"), {"name": username}
    ).one_or_none()
    return (row.id, row.password_hash) if row else None


def get_user(db: Session, user_id: int) -> tuple[str, bool] | None:
    """(아이디, 온보딩 완료 여부)."""
    row = db.execute(
        text("SELECT username, onboarded_at IS NOT NULL AS onboarded FROM users WHERE id = :id"),
        {"id": user_id},
    ).one_or_none()
    return (row.username, row.onboarded) if row else None


def mark_onboarded(db: Session, user_id: int) -> None:
    """처음 완료한 시각만 남긴다 (이미 있으면 그대로)."""
    db.execute(
        text("UPDATE users SET onboarded_at = now() WHERE id = :id AND onboarded_at IS NULL"),
        {"id": user_id},
    )


def delete_user(db: Session, user_id: int) -> None:
    """밭·구역·기록·판정은 외래키 CASCADE로 함께 지워진다."""
    db.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
