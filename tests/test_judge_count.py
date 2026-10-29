from datetime import date

import pytest

from app.judgment.domain.rules import check_count, check_registration
from app.judgment.domain.schemas import Verdict
from tests.judge_support import make_input, reg, spray

OK, BLOCKED, NEEDS_CHECK = Verdict.OK, Verdict.BLOCKED, Verdict.NEEDS_CHECK
METHOD = "발생 초부터 경엽처리"
UNCONFIRMED = (
    "살포 기록에 빠진 것이 없는지 확인되지 않았습니다. "
    "기록을 입력하고 「누락 없음」을 선택해 주세요"
)
NO_PLANTING = "정식일이 없어 이번 작기 사용 횟수를 셀 수 없습니다. 정식일을 입력해 주세요"
OPEN = "남은 횟수 {r}회, 이번 사용 후 {after}회입니다 (최대 {mx}회)"
LAST = "남은 횟수 1회, 이번 사용 후 0회입니다 (최대 {mx}회). 이번이 마지막 사용입니다"
FULL = "{since}부터 {used}회 사용해 최대 {mx}회를 채웠습니다. 남은 횟수는 0회입니다"


def count(**kw):
    inp = make_input(**kw)
    return check_count(inp, check_registration(inp))


def cfacts(used=None, mx=None, remaining=None, after=None, since="2026-05-01",
           method=None, no_limit=False):
    return {
        "used": used,
        "max_uses": mx,
        "remaining": remaining,
        "remaining_after": after,
        "since": since,
        "item_name": "품목A",
        "strict_use_method": method,
        "no_limit": no_limit,
    }


def a(sid, month, day, **kw):  # 품목A(가1) 살포
    return spray(sid, "가1", date(2026, month, day), **kw)


def unreadable(raw):
    return f"최대 사용 횟수 기준을 읽지 못했습니다. 원문: {raw}"


OTHER_ITEM = [spray(1, "나2", date(2026, 6, 1), item_name="품목B")]
THREE = [a(1, 6, 1), a(2, 6, 15), a(3, 7, 1)]

COUNTED = [
    ("C1", OTHER_ITEM, 0, OK, OPEN.format(r=3, after=2, mx=3)),
    ("C2", [a(1, 6, 1)], 1, OK, OPEN.format(r=2, after=1, mx=3)),
    ("C3", [a(1, 6, 1), a(2, 6, 15)], 2, OK, LAST.format(mx=3)),
    ("C4", THREE, 3, BLOCKED, FULL.format(since="5월 1일", used=3, mx=3)),
    ("C5", [a(1, 4, 20), a(2, 6, 1)], 1, OK, OPEN.format(r=2, after=1, mx=3)),
    ("C7", [a(1, 6, 1, pesticide_id=10), a(2, 6, 10, pesticide_id=11)], 2, OK, LAST.format(mx=3)),
    ("C10", [], 0, OK, OPEN.format(r=3, after=2, mx=3)),
    ("C12", [a(1, 6, 1), a(2, 6, 1)], 2, OK, LAST.format(mx=3)),
    ("C14", [a(1, 4, 1)], 0, OK, OPEN.format(r=3, after=2, mx=3)),
    ("C17", THREE + [a(4, 8, 1)], 4, BLOCKED, FULL.format(since="5월 1일", used=4, mx=3)),
    ("on-planting-day", [a(1, 5, 1)], 1, OK, OPEN.format(r=2, after=1, mx=3)),
    ("day-before", [a(1, 4, 30)], 0, OK, OPEN.format(r=3, after=2, mx=3)),
]


@pytest.mark.parametrize(
    "history,used,status,message", [c[1:] for c in COUNTED], ids=[c[0] for c in COUNTED]
)
def test_counting_and_messages(history, used, status, message):
    r = count(history=history)

    assert (r.key, r.status, r.message) == ("count", status, message)
    remaining = max(3 - used, 0)
    after = None if status is BLOCKED else remaining - 1
    assert r.facts == cfacts(used, 3, remaining, after, method=METHOD)


def test_ok_evidence_is_the_strict_rows_raw_text():
    r = count()

    assert r.evidence.source_text == "3회 이내"
    assert r.evidence.data_asof == date(2026, 10, 1)


def test_c6_no_planting_date():
    r = count(planted_at=None, history=[a(1, 6, 1)])

    assert (r.status, r.message) == (NEEDS_CHECK, NO_PLANTING)
    assert r.facts == cfacts(since=None)


def test_c9_and_c15_unconfirmed_history():
    for history in ([], [a(1, 6, 1)]):
        r = count(history=history, history_confirmed=False)

        assert (r.status, r.message) == (NEEDS_CHECK, UNCONFIRMED)
        assert r.facts == cfacts()


def test_c16_planting_date_is_asked_before_the_confirmation():
    r = count(planted_at=None, history_confirmed=False)

    assert r.message == NO_PLANTING


def test_c11_unreadable_max_shows_the_raw_text_and_beats_the_planting_date():
    r = count(registrations=[reg(max_uses=None, use_num_raw="-")], planted_at=None)

    assert (r.status, r.message) == (NEEDS_CHECK, unreadable("-"))
    assert r.evidence.source_text == "-"
    assert r.facts == cfacts(since=None)


def test_check_row_with_numbers_is_still_unreadable():
    r = count(registrations=[reg(usage_type="CHECK", max_uses=3, use_num_raw="연1회")])

    assert (r.status, r.message) == (NEEDS_CHECK, unreadable("연1회"))


def test_unreadable_raw_text_is_the_first_unreadable_rows_and_none_when_empty():
    rows = [reg(max_uses=None, use_num_raw="A"), reg(max_uses=None, use_num_raw="B")]
    assert count(registrations=rows).evidence.source_text == "A"

    r = count(registrations=[reg(max_uses=None, use_num_raw=None)])
    assert r.message == unreadable("없음")
    assert r.evidence.source_text == "없음"


def test_c13_no_pest_takes_the_smallest_max_of_all_rows():
    rows = [reg(max_uses=5), reg(pest_id=2, pest_name="역병", max_uses=3)]
    r = count(pest_id=None, registrations=rows)

    assert r.facts["max_uses"] == 3


def test_c18_all_no_limit_ignores_planting_date_and_confirmation():
    row = reg(usage_type="NO_LIMIT", phi_days=None, max_uses=None, use_num_raw="-")
    r = count(registrations=[row], planted_at=None, history_confirmed=False)

    assert (r.status, r.message) == (
        OK,
        "사용 횟수 제한이 없는 약제입니다. 라벨의 사용 방법을 확인해 주세요",
    )
    assert r.facts == cfacts(since=None, no_limit=True)
    assert r.evidence.source_text == "-"


def test_c19_all_at_planting_still_counts():
    row = reg(usage_type="AT_PLANTING", phi_days=None, max_uses=1, use_num_raw="1회")
    r = count(registrations=[row], history=[])

    assert (r.status, r.facts["used"], r.facts["max_uses"]) == (OK, 0, 1)
    assert r.message == LAST.format(mx=1)


def test_c20_strictest_use_method_is_named():
    rows = [
        reg(max_uses=3, use_method="경엽처리"),
        reg(max_uses=1, use_num_raw="1회", use_method="무인항공"),
    ]
    r = count(registrations=rows)

    assert r.facts["strict_use_method"] == "무인항공"
    assert r.message == LAST.format(mx=1) + " (무인항공 기준)"
    assert r.evidence.source_text == "1회"


def test_c21_no_limit_row_is_left_out():
    rows = [reg(max_uses=3), reg(usage_type="NO_LIMIT", phi_days=None, max_uses=None)]
    r = count(registrations=rows)

    assert (r.status, r.facts["max_uses"], r.facts["no_limit"]) == (OK, 3, False)


def test_blocked_registration_makes_count_needs_check():
    r = count(registrations=[])

    assert (r.status, r.message) == (NEEDS_CHECK, "등록 정보가 없어 확인할 수 없습니다")
    assert r.evidence.source_text == "없음"
    assert r.facts == cfacts()


def test_blocked_message_names_the_year_when_it_differs():
    history = THREE + [spray(4, "가1", date(2025, 12, 1))]
    r = count(planted_at=date(2025, 11, 1), history=history)

    assert r.status is BLOCKED
    assert r.message.startswith("2025년 11월 1일부터 4회 사용해")
