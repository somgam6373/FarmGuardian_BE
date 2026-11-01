from sqlalchemy.orm import Session

from app.catalog.application import catalog_service
from app.core.errors import AppError
from app.inventory.infrastructure import repository


def _unknown_drug() -> AppError:
    # 보낸 값은 메시지에 넣지 않는다
    message = "알 수 없는 약제입니다"
    error = {"loc": ["body", "drug_id"], "msg": message, "type": "value_error"}
    return AppError("VALIDATION_ERROR", 422, message, {"errors": [error]})


def add_drug(db: Session, user_id: int, drug_id: int) -> bool:
    """창고에 담고 새로 담았는지 돌려준다 (이미 있으면 False). 카탈로그에 없는 약제는 422."""
    if catalog_service.get_pesticide(drug_id) is None:
        raise _unknown_drug()
    added = repository.add(db, user_id, drug_id)
    if added:
        db.commit()
    return added


def remove_drug(db: Session, user_id: int, drug_id: int) -> None:
    """창고에서 뺀다. 창고에 없으면 404.

    카탈로그에 없는 id는 있을 수 없으므로 DB를 보기 전에 404다 (큰 id는 int 열에서 넘친다).
    """
    if catalog_service.get_pesticide(drug_id) is None or not repository.remove(
        db, user_id, drug_id
    ):
        raise AppError("NOT_FOUND", 404, "찾을 수 없습니다")
    db.commit()


def list_drugs(db: Session, user_id: int) -> list[int]:
    return repository.list_ids(db, user_id)
