import functools
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.farm.application import zone_reader
from app.identity.domain.password import hash_password, verify_password
from app.identity.infrastructure import repository


@dataclass(frozen=True)
class Me:
    id: int
    username: str
    onboarded: bool


@functools.cache
def _dummy_hash() -> str:
    # 없는 아이디도 해시 검증을 한 번 하게 해서, 응답 시간으로 아이디 유무를 알 수 없게 한다
    return hash_password("dummy")


def register_user(db: Session, username: str, password: str) -> int | None:
    """사용자를 만들고 id를 돌려준다. 아이디가 이미 있으면 None. 커밋하지 않는다."""
    return repository.insert_user(db, username, hash_password(password))


def login(db: Session, username: str, password: str) -> tuple[int, str] | None:
    """(id, 아이디). 아이디 없음·비밀번호 틀림·잠긴 해시 모두 None이다."""
    # NUL은 PostgreSQL text에 넣을 수 없어 그런 아이디는 있을 수 없다 (DB 오류 대신 없는 아이디로)
    found = None if "\x00" in username else repository.find_by_username(db, username)
    if found is None:
        verify_password(password, _dummy_hash())
        return None
    user_id, stored = found
    return (user_id, username) if verify_password(password, stored) else None


def get_me(db: Session, user_id: int) -> Me:
    user = repository.get_user(db, user_id)
    if user is None:
        raise AppError("UNAUTHORIZED", 401, "인증이 필요합니다")
    return Me(user_id, user[0], user[1])


def complete_onboarding(db: Session, user_id: int) -> None:
    if get_me(db, user_id).onboarded:
        # 「누락 없음」은 정식일이 바뀌면 풀리므로, 한 번 끝낸 온보딩은 다시 따지지 않는다
        return
    zones = zone_reader.list_user_zones(db, user_id)
    unconfirmed = [zone.id for zone in zones if not zone.history_confirmed]
    if not zones or unconfirmed:
        message = "구역이 없거나 「누락 없음」이 확인되지 않은 구역이 있습니다"
        details = {"zone_count": len(zones), "unconfirmed_zone_ids": unconfirmed}
        raise AppError("ONBOARDING_INCOMPLETE", 422, message, details)
    repository.mark_onboarded(db, user_id)
    db.commit()


def withdraw(db: Session, user_id: int) -> None:
    repository.delete_user(db, user_id)
    db.commit()
