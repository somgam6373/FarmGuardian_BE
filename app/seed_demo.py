import argparse

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import SessionLocal


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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="개발용 시드 데이터를 넣는다")
    parser.add_argument(
        "--dev-user",
        action="store_true",
        required=True,
        help="밭·구역 없이 사용자 dev만 만든다 (프론트가 이 id를 X-User-Id로 쓴다)",
    )
    parser.parse_args(argv)
    with SessionLocal() as db:
        user_id = ensure_dev_user(db)
        db.commit()
    print(f"dev user id: {user_id}")


if __name__ == "__main__":
    main()
