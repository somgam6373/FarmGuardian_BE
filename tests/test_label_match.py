import pytest

from app.catalog.domain.entities import Moa, Pesticide
from app.catalog.domain.label_match import normalize, rank_candidates


def drug(id, name, item_name="품목", label=None):
    return Pesticide(id, name, item_name, Moa(label, None, None) if label else None)


def test_normalize_drops_spaces_punctuation_and_case():
    assert normalize(" 카브리오 (유제) ") == "카브리오유제"
    assert normalize("ABC-12") == "abc12"
    assert normalize(None) == ""
    assert normalize("·, -") == ""


def test_exact_read_ranks_first_with_score_one():
    other = drug(1, "보스", "디노테퓨란 입상수용제")
    target = drug(2, "카브리오", "피라클로스트로빈 유제")

    result = rank_candidates("카브리오", "피라클로스트로빈 유제", [other, target])

    assert result[0].pesticide == target
    assert result[0].score == 1.0


def test_similar_brands_keep_the_neighbour_visible():
    boss, bosca = drug(1, "보스"), drug(2, "보스카")

    result = rank_candidates("보스", None, [bosca, boss])

    assert [c.pesticide.name for c in result] == ["보스", "보스카"]
    assert [c.score for c in result] == [1.0, 0.8]


def test_brand_and_product_together_keep_the_right_brand_on_top():
    right, wrong = drug(1, "AAA", "P"), drug(2, "BBB", "P")

    result = rank_candidates("AAA", "P", [wrong, right])

    assert [c.pesticide.name for c in result] == ["AAA", "BBB"]
    assert [c.score for c in result] == [1.0, 0.5]


def test_shared_brand_appears_once_per_drug():
    second = drug(1, "스퍽", "나유제")
    first = drug(2, "스퍽", "가유제")

    result = rank_candidates("스퍽", None, [second, first])

    assert [c.pesticide.item_name for c in result] == ["가유제", "나유제"]


def test_ties_follow_catalog_order_with_missing_moa_last():
    no_moa = drug(1, "보스")
    b = drug(2, "보스", label="나2")
    a = drug(3, "보스", label="가1")

    result = rank_candidates("보스", None, [no_moa, b, a])

    assert [c.pesticide.id for c in result] == [3, 2, 1]


@pytest.mark.parametrize("brand, product", [(None, None), ("  ", None), ("-·", "")])
def test_nothing_read_returns_empty(brand, product):
    assert rank_candidates(brand, product, [drug(1, "보스")]) == []


def test_cutoff_and_limit():
    drugs = [drug(i, "보스" if i == 0 else f"보스{i}") for i in range(7)]

    assert len(rank_candidates("보스", None, drugs, limit=5)) == 5
    strict = rank_candidates("보스", None, drugs, cutoff=0.99)
    assert [c.pesticide.id for c in strict] == [0]
