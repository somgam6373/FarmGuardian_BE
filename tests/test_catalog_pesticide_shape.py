from app.catalog.application import catalog_service as svc
from app.catalog.domain.entities import Moa, Pesticide
from app.catalog.presentation.schemas import PesticideBase, PesticideOut, pesticide_base


def all_drugs():
    return [e.pesticide for crop_id in (1, 2, 3) for e in svc.list_pesticides(crop_id)]


def test_every_drug_is_found_by_its_id():
    for drug in all_drugs():
        assert svc.get_pesticide(drug.id) == drug


def test_distinct_drug_count():
    assert len({d.id for d in all_drugs()}) == 1363


def test_unknown_ids_are_none():
    for pesticide_id in (0, -1, 999999):
        assert svc.get_pesticide(pesticide_id) is None


def test_pesticide_base_has_the_four_spec_fields():
    assert set(PesticideBase.model_fields) == {"id", "name", "item_name", "moa"}
    assert set(PesticideOut.model_fields) == {"id", "name", "item_name", "moa", "at_planting_only"}


def test_pesticide_base_converter():
    drug = Pesticide(7, "Brand", "Item", Moa("라3", "FRAC", "24"))

    assert pesticide_base(drug).model_dump() == {
        "id": 7,
        "name": "Brand",
        "item_name": "Item",
        "moa": {"label_kr": "라3", "system": "FRAC", "code": "24"},
    }
    assert pesticide_base(Pesticide(8, "B", "I", None)).moa is None
