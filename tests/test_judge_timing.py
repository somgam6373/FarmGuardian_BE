from datetime import date

import pytest

from app.judgment.domain.rules import check_registration, check_timing
from app.judgment.domain.schemas import Verdict
from tests.judge_support import TODAY, make_input, reg

OTHER = dict(pest_id=2, pest_name="역병")
OK, NEEDS_CHECK = Verdict.OK, Verdict.NEEDS_CHECK
BLOCKED, CAUTION = Verdict.BLOCKED, Verdict.CAUTION
NO_LIMIT_MESSAGE = "수확 전 사용 일수 제한이 없는 약제입니다. 라벨의 사용 방법을 확인해 주세요"


def timing(**kw):
    inp = make_input(**kw)
    return check_timing(inp, check_registration(inp))


def facts(phi=None, harvest=None, rows=1, method=None, no_limit=False, reason=None):
    out = {
        "phi_days": phi,
        "harvest_from": harvest,
        "rows": rows,
        "strict_use_method": method,
        "no_limit": no_limit,
    }
    return out if reason is None else {**out, "reason": reason}


def unreadable(raw):
    return f"수확 전 사용 기준을 읽지 못했습니다. 원문: {raw}"


def test_t1_base():
    r = timing()

    assert (r.key, r.status) == ("timing", OK)
    assert r.message == (
        "오늘 살포하면 10월 11일부터 수확할 수 있습니다 (수확 7일 전까지 사용)"
    )
    assert r.facts == facts(7, "2026-10-11", 1, "발생 초부터 경엽처리")
    assert r.evidence.source_text == "수확 7일 전까지"
    assert r.evidence.data_asof == date(2026, 10, 1)


def test_t2_phi_zero_is_harvest_day():
    r = timing(registrations=[reg(phi_days=0)])

    assert (r.status, r.message) == (OK, "수확 당일까지 사용할 수 있습니다")
    assert r.facts == facts(0, "2026-10-04", 1, "발생 초부터 경엽처리")


def test_t3_unreadable_phi_shows_the_raw_text():
    r = timing(registrations=[reg(phi_days=None, use_suittime_raw="수확 직전")])

    assert (r.status, r.message) == (NEEDS_CHECK, unreadable("수확 직전"))
    assert r.facts == facts(reason="unreadable")
    assert r.evidence.source_text == "수확 직전"


def test_t4_no_pest_uses_all_rows_and_the_strictest():
    rows = [reg(phi_days=7), reg(**OTHER, phi_days=14)]
    r = timing(pest_id=None, registrations=rows)

    assert r.status is OK
    assert r.facts == facts(14, "2026-10-18", 2, "발생 초부터 경엽처리")


def test_t5_other_pests_rows_are_ignored():
    rows = [reg(phi_days=7), reg(phi_days=10), reg(**OTHER, phi_days=30)]
    r = timing(registrations=rows)

    assert r.facts == facts(10, "2026-10-14", 2, "발생 초부터 경엽처리")


def test_t6_one_unreadable_row_makes_it_needs_check():
    r = timing(registrations=[reg(phi_days=7), reg(phi_days=None)])

    assert r.status is NEEDS_CHECK
    assert r.facts == facts(rows=2, reason="unreadable")


def test_t7_date_text_crosses_the_year():
    r = timing(today=date(2026, 12, 25), registrations=[reg(phi_days=14)])

    assert r.message == (
        "오늘 살포하면 2027년 1월 8일부터 수확할 수 있습니다 (수확 14일 전까지 사용)"
    )
    assert r.facts["harvest_from"] == "2027-01-08"


def test_t8_all_no_limit():
    row = reg(usage_type="NO_LIMIT", phi_days=None, use_suittime_raw="발생초기")
    r = timing(registrations=[row])

    assert (r.status, r.message) == (OK, NO_LIMIT_MESSAGE)
    assert r.facts == facts(no_limit=True)
    assert r.evidence.source_text == "발생초기"


def test_t9_all_at_planting():
    row = reg(usage_type="AT_PLANTING", phi_days=None, use_suittime_raw="정식기")
    r = timing(registrations=[row])

    assert r.status is NEEDS_CHECK
    assert r.message == (
        "이 약은 심을 때(정식기·파종기) 쓰는 약입니다. 수확 전 사용 기준이 없어 "
        "수확 가능일을 계산할 수 없습니다. 원문: 정식기"
    )
    assert r.evidence.source_text == "정식기"
    assert r.facts == facts(reason="at_planting")


def test_t10_planting_row_is_left_out_of_the_calculation():
    planting = reg(usage_type="AT_PLANTING", phi_days=None, use_suittime_raw="정식기")
    r = timing(registrations=[planting, reg(phi_days=7)])

    assert (r.status, r.facts["phi_days"], r.facts["rows"]) == (OK, 7, 2)


def test_t11_no_limit_row_is_left_out_of_the_calculation():
    rows = [reg(phi_days=7), reg(usage_type="NO_LIMIT", phi_days=None)]
    r = timing(registrations=rows)

    assert (r.status, r.facts["phi_days"], r.facts["no_limit"]) == (OK, 7, False)


def test_t12_check_row_without_numbers():
    row = reg(usage_type="CHECK", phi_days=None, use_suittime_raw="수확7일")
    r = timing(registrations=[row])

    assert (r.status, r.message) == (NEEDS_CHECK, unreadable("수확7일"))


def test_t13_strictest_use_method_is_named():
    rows = [reg(phi_days=14, use_method="경엽처리"), reg(phi_days=21, use_method="무인항공")]
    r = timing(registrations=rows)

    assert r.facts == facts(21, "2026-10-25", 2, "무인항공")
    assert r.message == (
        "오늘 살포하면 10월 25일부터 수확할 수 있습니다 (수확 21일 전까지 사용) (무인항공 기준)"
    )


def test_t14_planting_row_goes_first_then_only_no_limit_remains():
    rows = [
        reg(usage_type="AT_PLANTING", phi_days=None),
        reg(usage_type="NO_LIMIT", phi_days=None, use_suittime_raw="발생초기"),
    ]
    r = timing(registrations=rows)

    assert (r.status, r.facts["no_limit"], r.evidence.source_text) == (OK, True, "발생초기")


def test_t15_check_row_with_numbers_is_still_unreadable():  # 실제 데이터 use_id 3539
    row = reg(usage_type="CHECK", phi_days=50, use_suittime_raw="수확50일전")
    r = timing(registrations=[row])

    assert (r.status, r.message) == (NEEDS_CHECK, unreadable("수확50일전"))
    assert r.facts == facts(reason="unreadable")


def test_t16_raw_text_is_the_first_unreadable_rows_and_none_when_empty():
    rows = [reg(phi_days=None, use_suittime_raw="A"), reg(phi_days=None, use_suittime_raw="B")]
    assert timing(registrations=rows).evidence.source_text == "A"

    r = timing(registrations=[reg(phi_days=None, use_suittime_raw=None)])
    assert r.message == unreadable("없음")
    assert r.evidence.source_text == "없음"


def test_t17_equal_phi_picks_the_first_row_and_names_both_methods_apart():
    rows = [reg(phi_days=7, use_method="경엽처리"), reg(phi_days=7, use_method="무인항공")]
    r = timing(registrations=rows)

    assert r.facts["strict_use_method"] == "경엽처리"
    assert r.message.endswith("(경엽처리 기준)")


def test_t18_one_use_method_adds_no_suffix():
    rows = [reg(phi_days=7), reg(phi_days=10)]

    assert not timing(registrations=rows).message.endswith("기준)")


@pytest.mark.parametrize("kw", [{"registrations": [reg(**OTHER)]}, {"registrations": []}])
def test_blocked_registration_makes_timing_needs_check(kw):  # R2, R3의 ② 부분
    r = timing(**kw)

    assert (r.status, r.message) == (NEEDS_CHECK, "등록 정보가 없어 확인할 수 없습니다")
    assert r.facts == facts(rows=0, reason="not_registered")
    assert r.evidence.source_text == "없음"
    assert r.evidence.data_asof == date(2026, 10, 3)


@pytest.mark.parametrize(
    "harvest_at,status,margin",
    [
        (date(2026, 10, 10), BLOCKED, -1),
        (date(2026, 10, 11), CAUTION, 0),
        (date(2026, 10, 13), CAUTION, 2),
        (date(2026, 10, 14), OK, 3),
    ],
)
def test_margin_boundaries(harvest_at, status, margin):
    r = timing(harvest_at=harvest_at)

    assert (r.status, r.facts["margin_days"], r.facts["harvest_at"]) == (
        status,
        margin,
        harvest_at.isoformat(),
    )
    assert r.facts["phi_days"] == 7 and r.facts["harvest_from"] == "2026-10-11"


def test_margin_messages():
    assert timing(harvest_at=date(2026, 10, 10)).message == (
        "수확 예정일(10월 10일)까지 6일 남아 수확 7일 전까지 사용하는 기준을 지킬 수 없습니다"
    )
    assert timing(harvest_at=date(2026, 10, 11)).message == (
        "수확 예정일(10월 11일)까지 여유가 0일입니다 (수확 7일 전까지 사용)"
    )
    ok = timing(harvest_at=date(2026, 10, 14))
    assert ok.message == "오늘 살포하면 10월 11일부터 수확할 수 있습니다 (수확 7일 전까지 사용)"


def test_a_harvest_date_in_the_past_is_blocked_with_its_own_message():
    r = timing(harvest_at=date(2026, 10, 1))

    assert (r.status, r.message) == (BLOCKED, "수확 예정일(10월 1일)이 지났습니다")
    assert r.facts["margin_days"] == -10


def test_phi_zero_on_the_harvest_day_is_caution():
    r = timing(registrations=[reg(phi_days=0)], harvest_at=TODAY)

    assert (r.status, r.facts["margin_days"]) == (CAUTION, 0)


def test_the_method_suffix_follows_the_margin_message():
    rows = [reg(phi_days=14), reg(phi_days=21, use_method="무인항공")]
    r = timing(registrations=rows, harvest_at=date(2026, 10, 22))

    assert r.status is BLOCKED
    assert r.message.endswith("기준을 지킬 수 없습니다 (무인항공 기준)")


def test_no_harvest_date_changes_nothing():
    r = timing()

    assert r.facts == facts(7, "2026-10-11", 1, "발생 초부터 경엽처리")
    assert r.status is OK


@pytest.mark.parametrize(
    "kw,status",
    [
        (dict(registrations=[reg(phi_days=None, usage_type="NO_LIMIT")]), OK),
        (dict(registrations=[reg(phi_days=None, usage_type="AT_PLANTING")]), NEEDS_CHECK),
        (dict(registrations=[reg(phi_days=None, use_suittime_raw="수확 직전")]), NEEDS_CHECK),
        (dict(registrations=[reg(**OTHER)]), NEEDS_CHECK),  # ① BLOCKED
    ],
    ids=["no-limit", "at-planting", "unreadable", "not-registered"],
)
def test_other_paths_ignore_the_harvest_date(kw, status):
    r = timing(harvest_at=date(2026, 10, 5), **kw)

    assert r.status is status
    assert "margin_days" not in r.facts and "harvest_at" not in r.facts
