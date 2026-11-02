from collections import Counter

import pytest

from app.catalog.application import catalog_service as svc
from app.catalog.domain.pesticide_fields import form_of, kind_of
from app.catalog.infrastructure.static_data import load


@pytest.mark.parametrize(
    "item_name,form",
    [
        ("아미설브롬 입상수화제", "입상수화제"),
        ("피리달릴.스피네토람 유탁제", "유탁제"),
        ("공백없음", None),
    ],
)
def test_form_is_the_last_word_of_the_item_name(item_name, form):
    assert form_of(item_name) == form


@pytest.mark.parametrize(
    "usage,kind",
    [("살충", "insecticide"), ("살균", "fungicide"), ("균충", "both"), ("제초", None)],
)
def test_kind_follows_the_usage_column(usage, kind):
    assert kind_of(usage) == kind


def test_every_drug_has_company_form_kind_and_ingredients():
    drugs = svc.all_pesticides()

    assert len(drugs) == 1363
    assert all(d.company and d.form and d.kind and d.ingredients for d in drugs)
    assert Counter(d.kind for d in drugs) == {"insecticide": 763, "fungicide": 583, "both": 17}


def test_company_of_a_multi_company_drug_is_the_first_rows_company():
    key = ("비펜트린 입제", "스퍽")
    rows = [u for u in load("pesticide_use") if (u["product"], u["brand"]) == key]
    drug = next(d for d in svc.all_pesticides() if (d.item_name, d.name) == key)

    assert len({u["company"] for u in rows}) > 1
    assert drug.company == min(rows, key=lambda u: u["use_id"])["company"]


def test_ingredients_follow_the_use_ingredient_order():
    drug = next(d for d in svc.all_pesticides() if "." in d.item_name and len(d.ingredients) >= 2)
    key = (drug.item_name, drug.name)
    first = min(
        (u for u in load("pesticide_use") if (u["product"], u["brand"]) == key),
        key=lambda u: u["use_id"],
    )
    names = {i["ingredient_id"]: i["name"] for i in load("ingredient")}
    rows = sorted(
        (r for r in load("use_ingredient") if r["use_id"] == first["use_id"]),
        key=lambda r: r["seq"],
    )

    assert drug.ingredients == tuple(names[r["ingredient_id"]] for r in rows)
