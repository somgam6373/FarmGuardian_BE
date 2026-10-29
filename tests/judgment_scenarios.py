from datetime import date
from functools import cache

from app.catalog.application import catalog_service as catalog
from app.catalog.infrastructure.static_data import load
from app.judgment.application import service

CROPS = (1, 2, 3)
TODAY = date(2026, 10, 29)
PLANTED = date(2026, 4, 1)


def pool(crop_id, pest_id):
    return [e.pesticide for e in catalog.list_pesticides(crop_id, pest_id)]


@cache
def pests_with_drugs(crop_id):
    pest_ids = [p["pest_id"] for p in load("pest") if p["crop_id"] == crop_id]
    return [pest_id for pest_id in pest_ids if pool(crop_id, pest_id)]


@cache
def unregistered_drug(crop_id=1):
    every = {e.pesticide.id: e.pesticide for c in CROPS for e in catalog.list_pesticides(c)}
    return next(d for d in every.values() if not catalog.get_registrations(d.id, crop_id))


def assess(**overrides):
    args = {
        "crop_id": 1,
        "planted_at": PLANTED,
        "history_confirmed": True,
        "history": [],
        "pesticide_id": None,
        "pest_id": None,
        "today": TODAY,
    }
    return service.assess(**{**args, **overrides})


@cache
def pest_with_alternatives(crop_id=1):
    chosen = unregistered_drug(crop_id)
    for pest_id in pests_with_drugs(crop_id):
        if assess(crop_id=crop_id, pesticide_id=chosen.id, pest_id=pest_id).alternatives:
            return pest_id
    raise LookupError("no pest with alternatives")


@cache
def counting_selection(crop_id=1):
    for pest_id in pests_with_drugs(crop_id):
        for drug in pool(crop_id, pest_id):
            rows = [r for r in catalog.get_registrations(drug.id, crop_id) if r.pest_id == pest_id]
            if rows and all(r.parse_status == "ok" and (r.max_uses or 0) >= 2 for r in rows):
                return pest_id, drug
    raise LookupError("no counting selection")
