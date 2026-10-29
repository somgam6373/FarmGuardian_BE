import pytest

from app.catalog.infrastructure.static_data import load
from app.judgment.domain.rules import moa_label, rotation_rule
from app.judgment.domain.schemas import Moa

MULTI = "FRAC Multi-site Guidelines"
EXCEPTION = "IRAC 예외 그룹"
PHENYL = "FRAC Phenylamides (last updated March 2020)"
CAA = "FRAC CAA WG 2026 회의록 3.2절"
IRAC = "IRAC MoA Classification v11.5 (Feb 2026)"
PLS = "농식품부 PLS 안내"
N, C = "NO_LIMIT", "CONSECUTIVE"

TABLE = [
    ("카", "FRAC", N, None, MULTI),
    *[(f"8{c}", "IRAC", N, None, EXCEPTION) for c in "abcdef"],
    ("13", "IRAC", N, None, EXCEPTION),
    ("미분류(살충제)", None, N, None, EXCEPTION),
    ("가1", "FRAC", C, 2, PHENYL),
    ("아5", "FRAC", C, 2, CAA),
    ("28", "IRAC", C, 2, IRAC),
    ("다3", "FRAC", C, 1, PLS),
    ("생1", "FRAC", C, 1, PLS),
    ("생2", "FRAC", C, 1, PLS),
    ("미분류(살균제)", None, C, 1, PLS),
    ("미분류", None, C, 1, PLS),
    ("가5", None, C, 1, PLS),
]


@pytest.mark.parametrize("label,system,kind,max_consecutive,source", TABLE)
def test_rule_table(label, system, kind, max_consecutive, source):
    rule = rotation_rule(Moa(label_kr=label, system=system))

    assert (rule.kind, rule.max_consecutive, rule.source) == (kind, max_consecutive, source)


@pytest.mark.parametrize(
    "label,kind,max_consecutive,source",
    [
        ("카+가1", C, 2, PHENYL),
        ("카+라3", C, 1, PLS),
        ("카+13", N, None, MULTI),
        ("13+22b", C, 1, PLS),
        ("카+아5+다3", C, 1, PLS),
        ("가1+아5", C, 2, PHENYL),
    ],
)
def test_compound_label_uses_the_strictest_part(label, kind, max_consecutive, source):
    rule = rotation_rule(Moa(label_kr=label))

    assert (rule.kind, rule.max_consecutive, rule.source) == (kind, max_consecutive, source)


def test_rule_table_equals_rotation_rule_json():  # RULE1
    sample = {  # rule_id → 그 규칙에 해당하는 계열
        1: Moa(label_kr="28", system="IRAC", code="28"),
        2: Moa(label_kr="다3", system="FRAC", code="3"),
        3: Moa(label_kr="가1", system="FRAC", code="4"),
        4: Moa(label_kr="아5", system="FRAC", code="40"),
        5: Moa(label_kr="카", system="FRAC", code="M"),
        6: Moa(label_kr="13", system="IRAC", code="13"),
    }
    rows = load("rotation_rule")

    assert {r["rule_id"] for r in rows} == set(sample)
    for r in rows:
        rule = rotation_rule(sample[r["rule_id"]])
        assert rule.source == r["source"]
        assert rule.max_consecutive == r["max_consecutive"]
        assert (rule.kind == N) == (r["max_consecutive"] is None)


def test_every_moa_row_gets_a_rule_and_only_four_labels_are_unlimited():
    unlimited = set()
    for m in load("moa"):
        system, _, code = (m["intl_code"] or "").partition(" ")
        moa = Moa(label_kr=m["kr_code"], system=system or None, code=code or None)
        if rotation_rule(moa).kind == N:
            unlimited.add(m["kr_code"])

    assert unlimited == {"카", "8f", "13", "미분류(살충제)"}


def test_moa_label():
    assert moa_label(Moa(label_kr="가1", system="FRAC", code="4")) == "가1 (FRAC 4)"
    assert moa_label(Moa(label_kr="카+가1")) == "카+가1"
    assert moa_label(Moa(label_kr="가1", system="FRAC")) == "가1"
