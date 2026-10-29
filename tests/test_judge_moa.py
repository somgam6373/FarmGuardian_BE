from datetime import date

import pytest

from app.judgment.domain.rules import check_moa
from app.judgment.domain.schemas import Moa, Verdict
from tests.judge_support import make_input, recent, spray

PHENYL = "FRAC Phenylamides (last updated March 2020)"
OK, CAUTION, NEEDS_CHECK = Verdict.OK, Verdict.CAUTION, Verdict.NEEDS_CHECK
LABEL = "가1 (FRAC 4)"
UNCONFIRMED = (
    "살포 기록에 빠진 것이 없는지 확인되지 않았습니다. "
    "기록을 입력하고 「누락 없음」을 선택해 주세요"
)
NO_LIMIT_TEXT = "같은 계열을 반복해도 제한이 없는 계열입니다"


def run(**kw):
    return check_moa(make_input(**kw))


def mfacts(label=LABEL, rule="CONSECUTIVE", mx=2, consecutive=0, unknown=0, window=()):
    return {
        "label": label,
        "rule": rule,
        "max_consecutive": mx,
        "consecutive": consecutive,
        "unknown": unknown,
        "window": list(window),
    }


def win(rec_id, iso, label):
    return {"id": rec_id, "sprayed_on": iso, "item_name": "품목A", "label": label}


def test_m1_no_history():
    r = run(history=[])

    assert (r.key, r.status, r.message) == ("moa", OK, "살포 이력이 없습니다")
    assert r.facts == mfacts()
    assert r.evidence.source_text == PHENYL
    assert r.evidence.data_asof == date(2026, 10, 1)


def test_m2_unconfirmed_without_history():
    r = run(history=[], history_confirmed=False)

    assert (r.status, r.message) == (NEEDS_CHECK, UNCONFIRMED)


def test_m3_one_in_a_row_is_ok():
    r = run(history=recent("가1", "나2", "가1"))

    assert r.status is OK
    assert r.message == f"{LABEL} — 직전까지 같은 계열을 연속 1회 사용했습니다 (연속 2회까지 기준)"
    assert r.facts["consecutive"] == 1
    assert r.evidence.source_text == PHENYL


def test_m4_reaching_the_limit_is_caution_with_a_three_record_window():
    r = run(history=recent("가1", "가1", "나2"))

    assert r.status is CAUTION
    assert r.message == (
        f"{LABEL} — 직전까지 같은 계열을 연속 2회 사용했습니다. "
        "연속 2회까지가 기준이라 같은 작용기작이 반복됩니다"
    )
    assert r.facts == mfacts(
        consecutive=2,
        window=[
            win(3, "2026-09-01", "가1"),
            win(2, "2026-08-31", "가1"),
            win(1, "2026-08-30", "나2"),
        ],
    )


def test_m5_newest_record_of_another_group_breaks_the_run():
    r = run(history=recent("나2", "가1", "가1"))

    assert (r.status, r.message) == (OK, f"{LABEL} — 직전 살포는 다른 계열입니다")
    assert r.facts["consecutive"] == 0


def test_m6_chosen_drug_without_moa():
    r = run(moa=None, history=recent("가1", "가1"))

    assert (r.status, r.message) == (
        NEEDS_CHECK,
        "이 약제의 작용기작 정보가 없어 비교할 수 없습니다",
    )
    assert r.evidence.source_text == "없음"
    assert r.facts == {
        "label": None,
        "rule": None,
        "max_consecutive": None,
        "consecutive": None,
        "unknown": None,
        "window": [],
    }


def test_m7_unknown_record_breaks_the_run_and_is_counted():
    r = run(history=recent(None, "가1", "가1"))

    assert r.status is OK
    assert r.message == f"{LABEL} — 직전 살포는 다른 계열입니다 (작용기작 미상 1건 포함)"
    assert (r.facts["consecutive"], r.facts["unknown"]) == (0, 1)
    assert r.facts["window"][0]["label"] is None


def test_m8_same_day_records_are_ordered_by_id():
    history = [
        spray(3, "가1", date(2026, 8, 30)),
        spray(4, "가1", date(2026, 9, 1)),
        spray(5, "나2", date(2026, 9, 1)),
    ]
    r = run(history=history)

    assert [w["id"] for w in r.facts["window"]] == [5, 4, 3]
    assert (r.status, r.facts["consecutive"]) == (OK, 0)


def test_m9_unconfirmed_history_is_needs_check_not_caution():
    r = run(history=recent("가1", "가1"), history_confirmed=False)

    assert (r.status, r.message) == (NEEDS_CHECK, UNCONFIRMED)
    assert r.facts["consecutive"] == 2  # 이력에서 계산한 값은 보여 준다


FRAC_M = Moa(label_kr="카", system="FRAC", code="M")
IRAC_8F = Moa(label_kr="8f", system="IRAC", code="8F")
IRAC_28 = Moa(label_kr="28", system="IRAC", code="28")
FRAC_3 = Moa(label_kr="다3", system="FRAC", code="3")
FRAC_4 = Moa(label_kr="가1", system="FRAC", code="4")


@pytest.mark.parametrize(
    "chosen,labels,status,rule,mx,consecutive,message",
    [
        (FRAC_M, ["카", "카", "카"], OK, "NO_LIMIT", None, 3, f"카 (FRAC M) — {NO_LIMIT_TEXT}"),
        (IRAC_8F, ["8f"] * 3, OK, "NO_LIMIT", None, 3, f"8f (IRAC 8F) — {NO_LIMIT_TEXT}"),
        (IRAC_28, ["28", "28", "나2"], CAUTION, "CONSECUTIVE", 2, 2, None),
        (IRAC_28, ["28", "나2"], OK, "CONSECUTIVE", 2, 1, None),
        (FRAC_3, ["다3"], CAUTION, "CONSECUTIVE", 1, 1, None),
        (Moa(label_kr="카+가1"), ["카+가1"] * 2, CAUTION, "CONSECUTIVE", 2, 2, None),
        (Moa(label_kr="카+라3"), ["카+라3"], CAUTION, "CONSECUTIVE", 1, 1, None),
        (FRAC_4, ["가1"] * 3, CAUTION, "CONSECUTIVE", 2, 3, None),
    ],
    ids=["M10", "M11", "M12", "M13", "M14", "M15", "M16", "M17"],
)
def test_m10_to_m17_rules_by_group(chosen, labels, status, rule, mx, consecutive, message):
    r = run(moa=chosen, history=recent(*labels))

    assert r.status is status
    assert (r.facts["rule"], r.facts["max_consecutive"], r.facts["consecutive"]) == (
        rule,
        mx,
        consecutive,
    )
    if message:
        assert r.message == message


def test_no_limit_wins_over_an_empty_history():
    r = run(moa=FRAC_M, history=[])

    assert r.message == f"카 (FRAC M) — {NO_LIMIT_TEXT}"


def test_window_has_at_most_three_records_and_unknown_counts_only_those():
    r = run(history=recent("가1", "가1", "가1", None))

    assert len(r.facts["window"]) == 3
    assert (r.facts["consecutive"], r.facts["unknown"]) == (3, 0)


def test_only_the_newest_run_counts():
    r = run(history=recent("가1", "나2", "나2"))

    assert r.facts["consecutive"] == 1


def test_unknown_note_is_added_to_the_caution_message_too():
    r = run(history=recent("가1", "가1", None))

    assert r.status is CAUTION
    assert r.message.endswith("같은 작용기작이 반복됩니다 (작용기작 미상 1건 포함)")


def test_works_without_planting_date_and_ignores_registration():  # C6의 ④ 부분
    r = run(planted_at=None, registrations=[], history=recent("가1"))

    assert r.status is OK
    assert r.message == f"{LABEL} — 직전까지 같은 계열을 연속 1회 사용했습니다 (연속 2회까지 기준)"
