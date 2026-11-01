from pydantic import BaseModel, StrictInt


class InventoryIn(BaseModel):
    drug_id: StrictInt  # JSON true를 1로, "5"를 5로 받지 않는다


class InventoryItem(BaseModel):
    drug_id: int
