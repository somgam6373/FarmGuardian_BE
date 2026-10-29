import pytest

from app.catalog.application import catalog_service as svc
from app.catalog.domain.entities import Moa
from app.catalog.infrastructure.static_data import load
from app.core.errors import AppError

CROPS = [1, 2, 3]


def pair(entry):
    return (entry.pesticide.item_name, entry.pesticide.name)


def all_entries():
    return [e for crop_id in CROPS for e in svc.list_pesticides(crop_id)]


def raw_flags(crop_id, pest_id=None):
    """원본 행에서 직접 계산한 기준: (품목, 상표) → 심을 때만 여부."""
    pests = {p["pest_id"]: p["crop_id"] for p in load("pest")}
    status = {s["use_id"]: s["parse_status"] for s in load("safe_use_std")}
    rows = {}
    for u in load("pesticide_use"):
        if pests[u["pest_id"]] != crop_id or (pest_id and u["pest_id"] != pest_id):
            continue
        rows.setdefault((u["product"], u["brand"]), []).append(status[u["use_id"]])
    return {key: all(s == "stage" for s in found) for key, found in rows.items()}


def test_crops_in_id_order():
    crops = svc.list_crops()

    assert [(c.id, c.name) for c in crops] == [(1, "감자"), (2, "배추"), (3, "토마토")]


@pytest.mark.parametrize("crop_id,count", [(1, 508), (2, 1008), (3, 515)])
def test_drug_counts_per_crop(crop_id, count):
    assert len(svc.list_pesticides(crop_id)) == count


def test_ids_are_unique_inside_a_list():
    for crop_id in CROPS:
        ids = [e.pesticide.id for e in svc.list_pesticides(crop_id)]

        assert len(set(ids)) == len(ids)


def test_id_is_the_smallest_use_id_of_the_pair():
    entries = svc.list_pesticides(1)
    first = next(e for e in entries if pair(e) == ("아미설브롬 입상수화제", "엑사이도"))

    assert first.pesticide.id == 1


@pytest.mark.parametrize("crop_id,only,no_moa", [(1, 103, 3), (2, 171, 4), (3, 57, 5)])
def test_at_planting_only_and_missing_moa_counts(crop_id, only, no_moa):
    entries = svc.list_pesticides(crop_id)

    assert sum(e.at_planting_only for e in entries) == only
    assert sum(e.pesticide.moa is None for e in entries) == no_moa


def test_at_planting_only_matches_the_raw_rows_for_every_crop():
    for crop_id in CROPS:
        got = {pair(e): e.at_planting_only for e in svc.list_pesticides(crop_id)}

        assert got == raw_flags(crop_id)


@pytest.mark.parametrize("crop_id", CROPS)
def test_sort_order(crop_id):
    keys = [
        (
            e.pesticide.moa is None,
            e.pesticide.moa.label_kr if e.pesticide.moa else "",
            e.pesticide.item_name,
            e.pesticide.name,
        )
        for e in svc.list_pesticides(crop_id)
    ]

    assert keys == sorted(keys)


def test_moa_conversion_samples():
    entries = all_entries()
    by_label = {e.pesticide.moa.label_kr: e.pesticide.moa for e in entries if e.pesticide.moa}

    assert by_label["가1"] == Moa(label_kr="가1", system="FRAC", code="4")
    assert by_label["카"] == Moa(label_kr="카", system="FRAC", code="M 01~M 13")
    compound = next(m for label, m in by_label.items() if "+" in label)
    assert (compound.system, compound.code) == (None, None)
    no_intl = [m for m in by_label.values() if m.system is None and "+" not in m.label_kr]
    assert no_intl  # 국제 코드가 없는 단일 계열은 system·code가 null이다
    assert any(e.pesticide.moa is None for e in entries)


def test_pest_filter_narrows_the_list_and_keeps_ids():
    everything = {pair(e): e for e in svc.list_pesticides(1)}
    narrowed = svc.list_pesticides(1, 1)
    expected = {(u["product"], u["brand"]) for u in load("pesticide_use") if u["pest_id"] == 1}

    assert {pair(e) for e in narrowed} == expected
    assert len(narrowed) < len(everything)
    assert all(everything[pair(e)].pesticide.id == e.pesticide.id for e in narrowed)
    assert {pair(e): e.at_planting_only for e in narrowed} == raw_flags(1, 1)


def raises_not_found(*args):
    with pytest.raises(AppError) as info:
        svc.list_pesticides(*args)

    assert (info.value.status, info.value.code) == (404, "NOT_FOUND")


def test_unknown_crop_is_404():
    raises_not_found(99)


def test_unknown_pest_is_404():
    raises_not_found(1, 999999)


def test_pest_of_another_crop_is_404():
    other = next(p["pest_id"] for p in load("pest") if p["crop_id"] == 2)

    raises_not_found(1, other)
