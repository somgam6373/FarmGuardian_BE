from datetime import date

from app.judgment.domain.rules import rotation_summary
from app.judgment.domain.schemas import Moa, SprayRecord
from tests.judge_support import spray

PLANTED = date(2026, 5, 1)


def labels(summary):
    return [(i.moa.label_kr if i.moa else None, i.count) for i in summary.items]


def history(*specs):  # (계열, 월, 일): id는 1부터
    return [spray(n, label, date(2026, m, d)) for n, (label, m, d) in enumerate(specs, start=1)]


def test_rt1_counts_only_records_after_planting():
    records = history(
        ("가1", 6, 1),
        ("가1", 6, 2),
        ("가1", 6, 3),
        ("가1", 6, 4),
        ("가1", 4, 20),
        ("나2", 7, 1),
        ("나2", 7, 2),
        (None, 8, 1),
    )
    s = rotation_summary(records, PLANTED)

    assert (s.window_start, s.total) == (PLANTED, 7)
    assert labels(s) == [("가1", 4), ("나2", 2), (None, 1)]


def test_rt2_no_history():
    s = rotation_summary([], PLANTED)

    assert (s.total, s.items) == (0, [])


def test_rt3_no_planting_date_uses_the_whole_history():
    records = [
        spray(1, "가1", date(2025, 8, 1)),
        spray(2, "가1", date(2026, 6, 1)),
        spray(3, "나2", date(2026, 7, 1)),
    ]
    s = rotation_summary(records, None)

    assert (s.window_start, s.total) == (None, 3)
    assert labels(s) == [("가1", 2), ("나2", 1)]


def test_record_on_planting_day_counts_and_the_day_before_does_not():
    assert rotation_summary(history(("가1", 5, 1)), PLANTED).total == 1
    assert rotation_summary(history(("가1", 4, 30)), PLANTED).total == 0


def test_history_only_before_planting_gives_an_empty_summary():
    s = rotation_summary(history(("가1", 3, 1), ("나2", 4, 1)), PLANTED)

    assert (s.window_start, s.total, s.items) == (PLANTED, 0, [])


def test_ties_are_ordered_by_label():
    s = rotation_summary(history(("나2", 6, 1), ("가1", 6, 2)), PLANTED)

    assert labels(s) == [("가1", 1), ("나2", 1)]


def test_unknown_group_is_last_even_with_the_most_records():
    records = history((None, 6, 1), (None, 6, 2), (None, 6, 3), ("가1", 6, 4))
    s = rotation_summary(records, PLANTED)

    assert labels(s) == [("가1", 1), (None, 3)]


def test_same_label_with_different_system_merges_using_the_newest_moa():
    old = SprayRecord(
        id=1,
        pesticide_id=10,
        item_name="품목A",
        sprayed_on=date(2026, 6, 1),
        moa=Moa(label_kr="가1"),
    )
    new = SprayRecord(
        id=2,
        pesticide_id=10,
        item_name="품목A",
        sprayed_on=date(2026, 6, 2),
        moa=Moa(label_kr="가1", system="FRAC", code="4"),
    )
    s = rotation_summary([old, new], PLANTED)

    assert len(s.items) == 1
    assert s.items[0].count == 2
    assert s.items[0].moa == Moa(label_kr="가1", system="FRAC", code="4")


def test_counts_records_not_drugs():
    records = [
        spray(1, "가1", date(2026, 6, 1), item_name="품목A"),
        spray(2, "가1", date(2026, 6, 2), item_name="품목B", pesticide_id=11),
    ]

    assert labels(rotation_summary(records, PLANTED)) == [("가1", 2)]


def test_serializes_to_the_spec_shape():
    s = rotation_summary(history(("가1", 6, 1), ("가1", 6, 2), (None, 6, 3)), PLANTED)

    assert s.model_dump(mode="json") == {
        "window_start": "2026-05-01",
        "total": 3,
        "items": [
            {"moa": {"label_kr": "가1", "system": None, "code": None}, "count": 2},
            {"moa": None, "count": 1},
        ],
    }


def test_input_history_is_not_changed():
    records = history(("가1", 6, 3), ("나2", 6, 1), ("가1", 6, 2))
    before = list(records)

    rotation_summary(records, PLANTED)

    assert records == before
