import re
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy import TextClause, text
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import AppError

# ASCII 숫자만, 최대 18자리 (bigint 범위 안). 0·앞자리 0·부호·소수점은 받지 않는다
_USER_ID = re.compile(r"[1-9][0-9]{0,17}")

_OWNED_FIELD = text("SELECT 1 FROM field WHERE id = :id AND user_id = :uid")
_OWNED_ZONE = text("SELECT 1 FROM zone WHERE id = :id AND user_id = :uid")


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


def _require_owned(db: Session, stmt: TextClause, resource_id: int, user_id: int) -> int:
    # 남의 것과 없는 것을 구분하지 않는다 (존재 여부가 새지 않게)
    if db.scalar(stmt, {"id": resource_id, "uid": user_id}) is None:
        raise AppError("NOT_FOUND", 404, "찾을 수 없습니다")
    return resource_id


def get_owned_field(
    field_id: int,
    user_id: Annotated[int, Depends(current_user)],
    db: Session = Depends(get_db),
) -> int:
    return _require_owned(db, _OWNED_FIELD, field_id, user_id)


def get_owned_zone(
    zone_id: int,
    user_id: Annotated[int, Depends(current_user)],
    db: Session = Depends(get_db),
) -> int:
    return _require_owned(db, _OWNED_ZONE, zone_id, user_id)
