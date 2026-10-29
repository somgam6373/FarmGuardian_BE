from datetime import date

import pytest
from pydantic import ValidationError

from app.judgment.domain.schemas import CheckResult, Evidence, Verdict
from tests.judge_support import make_input, reg


def test_verdict_values_are_the_spec_strings():
    assert [v.value for v in Verdict] == ["OK", "CAUTION", "BLOCKED", "NEEDS_CHECK"]


def test_check_result_serializes_to_the_spec_shape():
    result = CheckResult(
        key="registration",
        status=Verdict.OK,
        message="m",
        facts={"rows": 1},
        evidence=Evidence(source_text="없음", data_asof=date(2026, 10, 3)),
    )

    assert result.model_dump(mode="json") == {
        "key": "registration",
        "status": "OK",
        "message": "m",
        "facts": {"rows": 1},
        "evidence": {"source_text": "없음", "data_asof": "2026-10-03"},
    }


def test_unknown_usage_type_is_rejected():
    with pytest.raises(ValidationError):
        reg(usage_type="WEIRD")


def test_base_input_is_the_section_9_fixture():
    inp = make_input()

    assert (inp.today, inp.planted_at, inp.history_confirmed) == (
        date(2026, 10, 4),
        date(2026, 5, 1),
        True,
    )
    assert (inp.pest_id, inp.pesticide_id, inp.item_name) == (1, 10, "품목A")
    assert (inp.moa.label_kr, inp.moa.system, inp.moa.code) == ("가1", "FRAC", "4")
    assert (inp.history, inp.psis_asof) == ([], date(2026, 10, 3))
    [r] = inp.registrations
    assert (r.pest_id, r.pest_name, r.phi_days, r.max_uses) == (1, "탄저병", 7, 3)
    assert (r.use_suittime_raw, r.use_num_raw, r.dilut_raw) == (
        "수확 7일 전까지",
        "3회 이내",
        "1000배",
    )
    assert (r.use_method, r.usage_type, r.data_asof) == (
        "발생 초부터 경엽처리",
        "NORMAL",
        date(2026, 10, 1),
    )
