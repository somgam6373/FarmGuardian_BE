import pytest

from app.catalog.application import catalog_service as svc
from app.catalog.infrastructure.static_data import load
from app.core.errors import AppError

PARTS = {
    1: ["덩이", "뿌리", "잎", "줄기", "벌레", "열매"],
    2: ["뿌리", "잎", "줄기", "벌레"],
    3: ["뿌리", "잎", "줄기", "벌레", "열매"],
}
CANDIDATES = {
    (1, "덩이"): 13,
    (1, "뿌리"): 3,
    (1, "잎"): 11,
    (1, "줄기"): 7,
    (1, "벌레"): 12,
    (1, "열매"): 1,
    (2, "잎"): 38,
    (2, "뿌리"): 8,
    (2, "줄기"): 16,
    (2, "벌레"): 27,
    (3, "뿌리"): 6,
    (3, "잎"): 36,
    (3, "줄기"): 26,
    (3, "열매"): 22,
    (3, "벌레"): 17,
}


def pests_of(crop_id):
    return [p for p in load("pest") if p["crop_id"] == crop_id]


def registered_ids():
    return {u["pest_id"] for u in load("pesticide_use")}


@pytest.mark.parametrize("crop_id", [1, 2, 3])
def test_symptom_parts_in_the_fixed_order(crop_id):
    assert svc.list_symptom_parts(crop_id) == PARTS[crop_id]


@pytest.mark.parametrize("key,count", CANDIDATES.items())
def test_candidate_counts_per_crop_and_part(key, count):
    assert len(svc.list_candidates(*key)) == count


def test_candidates_match_the_raw_parts():
    for crop_id, part in CANDIDATES:
        expected = {p["pest_id"] for p in pests_of(crop_id) if part in (p["parts"] or [])}

        assert {c.id for c in svc.list_candidates(crop_id, part)} == expected


def test_a_pest_with_several_parts_appears_under_each():
    for part in ("잎", "줄기", "덩이"):  # 역병(8)의 부위
        assert 8 in {c.id for c in svc.list_candidates(1, part)}


def test_candidates_are_sorted_by_name_without_duplicates():
    for crop_id, part in CANDIDATES:
        cards = svc.list_candidates(crop_id, part)
        names = [c.name for c in cards]

        assert names == sorted(names)
        assert len({c.id for c in cards}) == len(names)


@pytest.mark.parametrize("crop_id,count", [(1, 25), (2, 43), (3, 23)])
def test_registered_pest_counts(crop_id, count):
    assert len(svc.list_pests(crop_id)) == count


def test_listed_pests_are_exactly_the_registered_pests_of_the_crop():
    for crop_id in (1, 2, 3):
        expected = {p["pest_id"] for p in pests_of(crop_id) if p["pest_id"] in registered_ids()}
        cards = svc.list_pests(crop_id)
        names = [c.name for c in cards]

        assert {c.id for c in cards} == expected
        assert names == sorted(names)


def test_registered_pests_without_a_pest_guide_entry_are_listed():
    no_guide = {
        p["pest_id"] for p in load("pest") if not p["has_doc"] and p["pest_id"] in registered_ids()
    }
    listed = {c.id for crop_id in (1, 2, 3) for c in svc.list_pests(crop_id)}

    assert no_guide and no_guide <= listed


def test_candidates_are_not_limited_to_registered_pests():
    candidates = {c.id for part in PARTS[3] for c in svc.list_candidates(3, part)}
    listed = {c.id for c in svc.list_pests(3)}

    assert len(candidates) == 43 and len(listed) == 23
    assert candidates - listed


def test_q_matches_a_name_substring():
    expected = sorted(
        p["name"] for p in pests_of(2) if "나방" in p["name"] and p["pest_id"] in registered_ids()
    )

    assert [c.name for c in svc.list_pests(2, "나방")] == expected
    assert expected


def test_q_is_trimmed_and_blank_means_everything():
    everything = [c.id for c in svc.list_pests(2)]

    assert [c.id for c in svc.list_pests(2, "  나방 ")] == [c.id for c in svc.list_pests(2, "나방")]
    assert [c.id for c in svc.list_pests(2, "")] == everything
    assert [c.id for c in svc.list_pests(2, "   ")] == everything


def test_q_without_a_match_gives_an_empty_list():
    assert svc.list_pests(2, "없는이름") == []


@pytest.mark.parametrize(
    "call",
    [
        lambda: svc.list_symptom_parts(99),
        lambda: svc.list_candidates(99, "잎"),
        lambda: svc.list_pests(99),
    ],
    ids=["symptom-parts", "candidates", "pests"],
)
def test_unknown_crop_is_404(call):
    with pytest.raises(AppError) as info:
        call()

    assert (info.value.status, info.value.code) == (404, "NOT_FOUND")


@pytest.mark.parametrize("crop_id,part", [(1, "없는부위"), (3, "덩이"), (2, "열매")])
def test_part_outside_the_crops_list_is_422(crop_id, part):
    with pytest.raises(AppError) as info:
        svc.list_candidates(crop_id, part)

    assert (info.value.status, info.value.code) == (422, "VALIDATION_ERROR")
    error = info.value.details["errors"][0]
    assert error["loc"] == ["query", "part"]
    assert part not in error["msg"]
