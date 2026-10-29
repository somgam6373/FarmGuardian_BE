from datetime import date
from pathlib import Path

import pytest

from app.judgment.domain.rules import calc_rows, check_registration, check_timing, format_date_kr
from tests.judge_support import make_input, reg

FORBIDDEN = ["추천", "예측", "예상", "가능성", "위험", "확률", "안전", "문제없"]
DOMAIN = Path(__file__).resolve().parents[1] / "app" / "judgment" / "domain"
OTHER = dict(pest_id=2, pest_name="역병")


@pytest.mark.parametrize(
    "types,kept",
    [
        (["AT_PLANTING", "NORMAL"], [1]),
        (["NORMAL", "NO_LIMIT"], [0]),
        (["AT_PLANTING", "NO_LIMIT"], [1]),
        (["AT_PLANTING", "AT_PLANTING"], [0, 1]),
        (["NO_LIMIT", "NO_LIMIT"], [0, 1]),
        (["AT_PLANTING", "NO_LIMIT", "NORMAL"], [2]),
        (["AT_PLANTING", "CHECK"], [1]),
    ],
)
def test_calc_rows_drops_planting_then_no_limit_only_while_rows_remain(types, kept):
    rows = [reg(usage_type=t, use_method=f"m{i}") for i, t in enumerate(types)]

    assert [r.use_method for r in calc_rows(rows)] == [f"m{i}" for i in kept]


def test_format_date_kr():
    assert format_date_kr(date(2026, 10, 11), today=date(2026, 10, 4)) == "10월 11일"
    assert format_date_kr(date(2027, 1, 8), today=date(2026, 12, 25)) == "2027년 1월 8일"


SCAN_INPUTS = [
    {},
    {"registrations": [reg(**OTHER)]},
    {"registrations": []},
    {"pest_id": None},
    {"registrations": [reg(phi_days=0)]},
    {"registrations": [reg(phi_days=None)]},
    {"registrations": [reg(usage_type="NO_LIMIT", phi_days=None)]},
    {"registrations": [reg(usage_type="AT_PLANTING", phi_days=None)]},
    {
        "registrations": [
            reg(phi_days=14, use_method="경엽처리"),
            reg(phi_days=21, use_method="무인항공"),
        ]
    },
    {"today": date(2026, 12, 25), "registrations": [reg(phi_days=14)]},
]


def test_no_forbidden_word_in_any_registration_or_timing_message():
    for kw in SCAN_INPUTS:
        inp = make_input(**kw)
        registration = check_registration(inp)
        for result in (registration, check_timing(inp, registration)):
            assert not [w for w in FORBIDDEN if w in result.message], result.message


def test_domain_imports_no_db_http_or_clock():
    text = "".join(p.read_text(encoding="utf-8") for p in DOMAIN.glob("*.py"))

    for word in ("sqlalchemy", "fastapi", "httpx", "datetime.now", "date.today"):
        assert word not in text
