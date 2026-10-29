from datetime import date

from app.judgment.domain.schemas import (
    CheckResult,
    Evidence,
    JudgeInput,
    Registration,
    Verdict,
)

NONE_TEXT = "없음"  # 근거 원문이 비었을 때 보여 줄 문구


def considered_rows(inp: JudgeInput) -> list[Registration]:
    """고려 대상 행: 고른 병해충의 행, 병해충을 안 골랐으면 전부. 입력 순서를 지킨다."""
    if inp.pest_id is None:
        return list(inp.registrations)
    return [r for r in inp.registrations if r.pest_id == inp.pest_id]


def rows_data_asof(inp: JudgeInput) -> date:
    """고려 대상 행 중 가장 오래된 기준일. 행이 없으면 입력의 기준일."""
    rows = considered_rows(inp)
    return min(r.data_asof for r in rows) if rows else inp.psis_asof


def check_registration(inp: JudgeInput) -> CheckResult:
    """① 등록: 이 작물·병해충에 등록된 약제인가."""
    data_asof = rows_data_asof(inp)

    def result(status: Verdict, message: str, facts: dict, source_text: str) -> CheckResult:
        return CheckResult(
            key="registration",
            status=status,
            message=message,
            facts=facts,
            evidence=Evidence(source_text=source_text, data_asof=data_asof),
        )

    if not inp.registrations:
        return result(
            Verdict.BLOCKED,
            "이 작물에는 등록되어 있지 않습니다",
            {"crop_registered": False},
            NONE_TEXT,
        )

    rows = considered_rows(inp)
    pests = sorted({r.pest_name for r in inp.registrations})
    listed = "등록 병해충: " + ", ".join(pests)

    if inp.pest_id is None:
        return result(
            Verdict.NEEDS_CHECK,
            "병해충을 지정하지 않아 등록 여부를 확인할 수 없습니다 (이 작물에는 등록되어 있습니다)",
            {"crop_registered": True, "pest_specified": False, "registered_pests": pests},
            listed,
        )
    if not rows:
        return result(
            Verdict.BLOCKED,
            f"이 병해충에는 등록되어 있지 않습니다 (이 작물에 등록된 병해충 {len(pests)}종)",
            {"crop_registered": True, "registered_pests": pests},
            listed,
        )

    first = rows[0]
    parts = [text for text in (first.use_method, first.dilut_raw) if text]
    return result(
        Verdict.OK,
        "이 병해충에 등록된 약제입니다",
        {"pest_specified": True, "rows": len(rows)},
        " · ".join(parts) or NONE_TEXT,
    )
