from datetime import date

from app.catalog.application import catalog_service as svc
from app.catalog.infrastructure.static_data import load


def all_drugs():
    return {
        e.pesticide.id: e.pesticide for crop_id in (1, 2, 3) for e in svc.list_pesticides(crop_id)
    }


def as_tuple(row):
    return (
        row.pest_id,
        row.pest_name,
        row.phi_days,
        row.max_uses,
        row.use_time,
        row.use_count,
        row.dilution,
        row.method,
        row.parse_status,
        row.base_date,
    )


def raw_index():
    """Independent join of the raw JSON: (product, brand, crop) -> rows by use_id."""
    std = {s["use_id"]: s for s in load("safe_use_std")}
    pests = {p["pest_id"]: p for p in load("pest")}
    index = {}
    for u in sorted(load("pesticide_use"), key=lambda u: u["use_id"]):
        s, pest = std[u["use_id"]], pests[u["pest_id"]]
        row = (
            u["pest_id"],
            pest["name"],
            s["phi_days"],
            s["max_count"],
            u["use_time"],
            u["use_count"],
            u["dilution"],
            u["method"],
            s["parse_status"],
            date.fromisoformat(s["base_date"]),
        )
        index.setdefault((u["product"], u["brand"], pest["crop_id"]), []).append(row)
    return index


def test_rows_match_an_independent_join_for_every_drug_and_crop():
    index = raw_index()
    for drug in all_drugs().values():
        for crop_id in (1, 2, 3):
            expected = index.get((drug.item_name, drug.name, crop_id), [])

            assert [as_tuple(r) for r in svc.get_registrations(drug.id, crop_id)] == expected


def test_every_pesticide_use_row_is_returned_exactly_once():
    total = sum(
        len(svc.get_registrations(drug.id, crop_id))
        for drug in all_drugs().values()
        for crop_id in (1, 2, 3)
    )

    assert total == len(load("pesticide_use")) == 4133


def test_unknown_drug_or_crop_has_no_rows():
    drug = next(iter(all_drugs().values()))

    assert svc.get_registrations(999999, 1) == []
    assert svc.get_registrations(drug.id, 99) == []


def test_data_asof_is_the_static_base_date():
    assert svc.data_asof() == date(2026, 10, 5)
