from collections import Counter

import pytest
from sqlalchemy import text

from app.catalog.infrastructure.static_data import load

COUNTS = {
    "crop": 3,
    "moa": 70,
    "ingredient": 216,
    "pest": 129,
    "pest_alias": 16,
    "pest_photo": 185,
    "pest_season": 51,
    "pesticide_use": 4133,
    "safe_use_std": 4133,
    "use_ingredient": 4949,
    "rotation_rule": 6,
    "virus_vector": 12,
}


@pytest.mark.parametrize("name,count", COUNTS.items())
def test_row_counts(name, count):
    assert len(load(name)) == count


@pytest.mark.parametrize(
    "name", ["app_user", "field", "zone", "spray_log", "", "../crop", "crop.json", "Crop"]
)
def test_unknown_name_is_rejected(name):
    with pytest.raises(ValueError):
        load(name)


def test_korean_text_is_decoded():
    assert [c["name"] for c in load("crop")] == ["감자", "배추", "토마토"]


def test_load_is_cached():
    assert load("crop") is load("crop")


def dangling(rows, key, valid):
    """Values of `key` (None ignored) that are not in `valid`."""
    return {r[key] for r in rows if r[key] is not None} - set(valid)


def test_dangling_ignores_none_and_reports_missing():
    assert dangling([{"a": 1}, {"a": 9}, {"a": None}], "a", {1}) == {9}


ID_KEYS = {
    "crop": "crop_id",
    "moa": "moa_id",
    "ingredient": "ingredient_id",
    "pest": "pest_id",
    "pest_alias": "alias_id",
    "pest_photo": "photo_id",
    "pest_season": "season_id",
    "pesticide_use": "use_id",
    "safe_use_std": "use_id",
    "rotation_rule": "rule_id",
}


@pytest.mark.parametrize("name,key", ID_KEYS.items())
def test_ids_are_unique(name, key):
    rows = load(name)

    assert len({r[key] for r in rows}) == len(rows)


def test_use_ids_run_1_to_n_in_both_use_files():
    expected = set(range(1, 4134))

    assert {r["use_id"] for r in load("pesticide_use")} == expected
    assert {r["use_id"] for r in load("safe_use_std")} == expected


REFERENCES = [
    ("use_ingredient", "use_id", "pesticide_use", "use_id"),
    ("use_ingredient", "ingredient_id", "ingredient", "ingredient_id"),
    ("ingredient", "moa_id", "moa", "moa_id"),
    ("pesticide_use", "pest_id", "pest", "pest_id"),
    ("pest", "crop_id", "crop", "crop_id"),
    ("pest_alias", "pest_id", "pest", "pest_id"),
    ("pest_photo", "pest_id", "pest", "pest_id"),
    ("pest_season", "pest_id", "pest", "pest_id"),
    ("virus_vector", "virus_pest_id", "pest", "pest_id"),
    ("virus_vector", "vector_pest_id", "pest", "pest_id"),
]


@pytest.mark.parametrize("child,key,parent,parent_key", REFERENCES)
def test_references_resolve(child, key, parent, parent_key):
    valid = {r[parent_key] for r in load(parent)}

    assert dangling(load(child), key, valid) == set()


def test_every_use_has_one_or_two_ingredients():
    per_use = Counter(r["use_id"] for r in load("use_ingredient"))

    assert set(per_use) == set(range(1, 4134))
    assert Counter(per_use.values()) == {1: 3317, 2: 816}


def test_parse_status_and_null_rules():
    rows = load("safe_use_std")

    assert Counter(r["parse_status"] for r in rows) == {
        "ok": 3531,
        "stage": 554,
        "no_std": 41,
        "failed": 7,
    }
    ok = [r for r in rows if r["parse_status"] == "ok"]
    assert all(r["phi_days"] is not None and r["max_count"] is not None for r in ok)
    no_phi = Counter(r["parse_status"] for r in rows if r["phi_days"] is None)
    assert no_phi == {"stage": 554, "no_std": 41, "failed": 6}
    no_max = Counter(r["parse_status"] for r in rows if r["max_count"] is None)
    assert no_max == {"no_std": 41, "failed": 1}
    assert {r["base_date"] for r in rows} == {"2026-10-05"}


def test_moa_codes_resolve_part_by_part():
    kr = {m["kr_code"] for m in load("moa")}
    codes = [u["moa_code"] for u in load("pesticide_use")]

    assert sum(1 for c in codes if not c) == 17  # 계열 코드가 없는 줄 (④ NEEDS_CHECK)
    assert all(set(c.split("+")) <= kr for c in codes if c)  # 복합 계열은 성분별로 풀린다


def test_known_gaps_are_pinned():
    assert sum(1 for i in load("ingredient") if i["moa_id"] is None) == 5
    assert sum(1 for v in load("virus_vector") if v["vector_pest_id"] is None) == 1


# use_id가 재번호된 JSON이 다시 오면 약제 id가 통째로 밀린다. 여기서 잡는다.
SAMPLES = [
    (1, "아미설브롬 입상수화제", "엑사이도"),
    (1000, "메탈락실엠 입제", "리도밀골드"),
    (2500, "트리플록시스트로빈 액상수화제", "프린트"),
    (4133, "피리다클로메틸 액상수화제", "알투도"),
]


def test_pesticide_identity_is_stable():
    uses = {u["use_id"]: u for u in load("pesticide_use")}

    for use_id, product, brand in SAMPLES:
        assert (uses[use_id]["product"], uses[use_id]["brand"]) == (product, brand)
    assert len({u["product"] for u in uses.values()}) == 652
    assert len({(u["product"], u["brand"]) for u in uses.values()}) == 1363


def test_crop_json_matches_the_crop_table(db):
    rows = db.execute(text("SELECT id, name FROM crop ORDER BY id")).all()

    assert [tuple(r) for r in rows] == [(c["crop_id"], c["name"]) for c in load("crop")]
