import re
from pathlib import Path

from sqlalchemy import text

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
        "inventory",
    }


def test_no_foreign_key_points_into_static_data():
    assert not re.search(r"REFERENCES\s+(pesticide|pest|moa|registration)\b", SCHEMA)


def test_spray_log_keeps_the_pest_and_the_cancel_time():
    spray_log = re.search(r"CREATE TABLE spray_log \((.*?)\n\);", SCHEMA, re.S).group(1)

    assert re.search(r"^\s+pest_id\s+int\b", spray_log, re.M)
    assert re.search(r"^\s+cancelled_at\s+timestamptz\b", spray_log, re.M)


def test_spray_log_table_has_the_pest_and_cancel_columns(db):
    columns = set(
        db.scalars(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'spray_log'"
            )
        )
    )

    assert {"pest_id", "cancelled_at"} <= columns  # 없으면 schema.sql의 ALTER TABLE을 적용한다


def test_field_keeps_the_address():
    field = re.search(r"CREATE TABLE field \((.*?)\n\);", SCHEMA, re.S).group(1)

    assert re.search(r"^\s+address\s+text\b", field, re.M)


def test_field_table_has_the_address_column(db):
    columns = set(
        db.scalars(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'field'"
            )
        )
    )

    assert "address" in columns  # 없으면 schema.sql의 ALTER TABLE을 적용한다


def test_zone_keeps_the_harvest_date():
    zone = re.search(r"CREATE TABLE zone \((.*?)\n\);", SCHEMA, re.S).group(1)

    assert re.search(r"^\s+harvest_at\s+date\b", zone, re.M)


def test_zone_table_has_the_harvest_column(db):
    columns = set(
        db.scalars(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'zone'"
            )
        )
    )

    assert "harvest_at" in columns  # 없으면 schema.sql의 ALTER TABLE을 적용한다


def test_inventory_table_matches_the_schema_file(db):
    columns = set(
        db.scalars(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'inventory'"
            )
        )
    )
    assert columns == {"user_id", "pesticide_id", "created_at"}

    key = list(
        db.scalars(
            text(
                "SELECT a.attname FROM pg_index i "
                "JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY (i.indkey) "
                "WHERE i.indrelid = 'inventory'::regclass AND i.indisprimary "
                "ORDER BY array_position(i.indkey::int2[], a.attnum)"
            )
        )
    )
    assert key == ["user_id", "pesticide_id"]

    foreign_keys = db.execute(
        text(
            "SELECT confrelid::regclass::text, confdeltype FROM pg_constraint "
            "WHERE conrelid = 'inventory'::regclass AND contype = 'f'"
        )
    ).all()
    assert [tuple(row) for row in foreign_keys] == [("users", "c")]  # c = ON DELETE CASCADE

    default = db.scalar(
        text(
            "SELECT column_default FROM information_schema.columns "
            "WHERE table_name = 'inventory' AND column_name = 'created_at'"
        )
    )
    assert "clock_timestamp" in default  # now()는 한 트랜잭션 안에서 같은 값이다
