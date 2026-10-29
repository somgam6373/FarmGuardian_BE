import re
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import AppError

# ASCII 숫자만, 최대 18자리 (bigint 범위 안). 0·앞자리 0·부호·소수점은 받지 않는다
_USER_ID = re.compile(r"[1-9][0-9]{0,17}")


def _unauthorized() -> AppError:
    # 헤더 없음·형식 오류·없는 사용자를 구분하지 않고, 받은 값도 돌려주지 않는다
    return AppError("UNAUTHORIZED", 401, "인증이 필요합니다")


def current_user(
    x_user_id: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
) -> int:
    if x_user_id is None or not _USER_ID.fullmatch(x_user_id):
        raise _unauthorized()
    user_id = db.scalar(text("SELECT id FROM users WHERE id = :id"), {"id": int(x_user_id)})
    if user_id is None:
        raise _unauthorized()
    return user_id
