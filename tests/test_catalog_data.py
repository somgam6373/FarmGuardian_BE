import pytest

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
