import re
from pathlib import Path

SCHEMA = (Path(__file__).resolve().parents[1] / "schema.sql").read_text(encoding="utf-8")


def test_only_user_data_tables_and_crop_remain():
    assert set(re.findall(r"CREATE TABLE (\w+)", SCHEMA)) == {
        "users",
        "crop",
        "field",
        "field_parcel",
        "zone",
        "spray_log",
        "judgment",
    }


def test_no_foreign_key_points_into_static_data():
    assert not re.search(r"REFERENCES\s+(pesticide|pest|moa|registration)\b", SCHEMA)
