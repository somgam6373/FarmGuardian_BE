from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.auth import current_user
from app.core.db import get_db
from app.inventory.application import service
from app.inventory.presentation.schemas import InventoryIn, InventoryItem

router = APIRouter(dependencies=[Depends(current_user)])

UserId = Annotated[int, Depends(current_user)]


@router.post("/inventory", response_model=InventoryItem, status_code=201)
def add_to_inventory(
    body: InventoryIn, response: Response, user_id: UserId, db: Session = Depends(get_db)
):
    if not service.add_drug(db, user_id, body.drug_id):  # 이미 있으면 다시 담지 않고 200
        response.status_code = 200
    return InventoryItem(drug_id=body.drug_id)


@router.get("/inventory", response_model=list[int])
def list_inventory(user_id: UserId, db: Session = Depends(get_db)):
    return service.list_drugs(db, user_id)


@router.delete("/inventory/{drug_id}", status_code=204)
def remove_from_inventory(drug_id: int, user_id: UserId, db: Session = Depends(get_db)):
    service.remove_drug(db, user_id, drug_id)
