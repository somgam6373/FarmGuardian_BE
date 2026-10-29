from datetime import date, timedelta

from app.judgment.domain.schemas import (
    CheckResult,
    Evidence,
    JudgeInput,
    Moa,
    Registration,
    RotationRule,
    Verdict,
)

NONE_TEXT = "없음"  # 근거 원문이 비었을 때 보여 줄 문구
NO_LIMIT_MESSAGE = "수확 전 사용 일수 제한이 없는 약제입니다. 라벨의 사용 방법을 확인해 주세요"


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


def calc_rows(rows: list[Registration]) -> list[Registration]:
    """계산용 행: 심을 때 행, 그다음 제한 없음 행을 뺀다. 빼고 나서 행이 남을 때만 뺀다."""
    for usage_type in ("AT_PLANTING", "NO_LIMIT"):
        kept = [r for r in rows if r.usage_type != usage_type]
        if kept:
            rows = kept
    return rows


def format_date_kr(d: date, today: date) -> str:
    """같은 해면 '10월 11일', 다른 해면 '2027년 1월 8일'."""
    if d.year == today.year:
        return f"{d.month}월 {d.day}일"
    return f"{d.year}년 {d.month}월 {d.day}일"


def _phi(row: Registration) -> int | None:
    # CHECK 행은 숫자가 있어도 읽지 못한 것으로 본다 (읽지 못한 행이 더 엄격할 수 있다)
    return None if row.usage_type == "CHECK" else row.phi_days


def check_timing(inp: JudgeInput, registration: CheckResult) -> CheckResult:
    """② 시기: 오늘 살포하면 언제부터 수확할 수 있는가. BLOCKED는 내지 않는다."""
    rows = considered_rows(inp)
    data_asof = rows_data_asof(inp)

    def result(status: Verdict, message: str, source_text: str | None, **facts) -> CheckResult:
        return CheckResult(
            key="timing",
            status=status,
            message=message,
            facts={
                "phi_days": None,
                "harvest_from": None,
                "rows": len(rows),
                "strict_use_method": None,
                "no_limit": False,
                **facts,
            },
            evidence=Evidence(source_text=source_text or NONE_TEXT, data_asof=data_asof),
        )

    if registration.status is Verdict.BLOCKED or not rows:
        return result(Verdict.NEEDS_CHECK, "등록 정보가 없어 확인할 수 없습니다", NONE_TEXT)

    calc = calc_rows(rows)
    if all(r.usage_type == "AT_PLANTING" for r in calc):
        raw = calc[0].use_suittime_raw or NONE_TEXT
        return result(
            Verdict.NEEDS_CHECK,
            "이 약은 심을 때(정식기·파종기) 쓰는 약입니다. "
            f"수확 전 사용 기준이 없어 수확 가능일을 계산할 수 없습니다. 원문: {raw}",
            raw,
        )
    if all(r.usage_type == "NO_LIMIT" for r in calc):
        return result(Verdict.OK, NO_LIMIT_MESSAGE, calc[0].use_suittime_raw, no_limit=True)

    unreadable = next((r for r in calc if _phi(r) is None), None)
    if unreadable is not None:
        raw = unreadable.use_suittime_raw or NONE_TEXT
        return result(Verdict.NEEDS_CHECK, f"수확 전 사용 기준을 읽지 못했습니다. 원문: {raw}", raw)

    phi = max(_phi(r) for r in calc)
    strict = next(r for r in calc if _phi(r) == phi)
    harvest_from = inp.today + timedelta(days=phi)
    methods = {r.use_method for r in calc if r.use_method}
    suffix = f" ({strict.use_method} 기준)" if len(methods) >= 2 and strict.use_method else ""
    if phi == 0:
        message = "수확 당일까지 사용할 수 있습니다" + suffix
    else:
        message = (
            f"오늘 살포하면 {format_date_kr(harvest_from, inp.today)}부터 수확할 수 있습니다 "
            f"(수확 {phi}일 전까지 사용)" + suffix
        )
    return result(
        Verdict.OK,
        message,
        strict.use_suittime_raw,
        phi_days=phi,
        harvest_from=harvest_from.isoformat(),
        strict_use_method=strict.use_method,
    )


# ④ 반복 규칙 표 (판정 규칙 §4 ④, 출처 문구는 rotation_rule.json과 같다).
# 계열 이름(label_kr)으로 찾는다: API 명세의 Moa에는 multi-site 표시가 없다.
_NO_LIMIT_SOURCES = {
    "카": "FRAC Multi-site Guidelines",
    **{f"8{c}": "IRAC 예외 그룹" for c in "abcdef"},
    "13": "IRAC 예외 그룹",
    "미분류(살충제)": "IRAC 예외 그룹",
}
_CONSECUTIVE_2 = {
    "가1": "FRAC Phenylamides (last updated March 2020)",
    "아5": "FRAC CAA WG 2026 회의록 3.2절",
}
_IRAC_SOURCE = "IRAC MoA Classification v11.5 (Feb 2026)"
_OTHER_SOURCE = "농식품부 PLS 안내"


def _part_rule(label: str, system: str | None) -> RotationRule:
    if label in _NO_LIMIT_SOURCES:
        return RotationRule(
            kind="NO_LIMIT", max_consecutive=None, source=_NO_LIMIT_SOURCES[label]
        )
    if label in _CONSECUTIVE_2:
        return RotationRule(
            kind="CONSECUTIVE", max_consecutive=2, source=_CONSECUTIVE_2[label]
        )
    if system == "IRAC":
        return RotationRule(kind="CONSECUTIVE", max_consecutive=2, source=_IRAC_SOURCE)
    return RotationRule(kind="CONSECUTIVE", max_consecutive=1, source=_OTHER_SOURCE)


def rotation_rule(moa: Moa) -> RotationRule:
    """계열의 반복 규칙. 복합 계열(+)은 성분별로 찾고 가장 엄격한 것을 쓴다."""
    if "+" not in moa.label_kr:
        return _part_rule(moa.label_kr, moa.system)
    # 성분의 system을 알 수 없으므로 이름만으로 찾는다 (모르면 「그 밖의 계열」)
    parts = [_part_rule(label, None) for label in moa.label_kr.split("+")]
    limited = [p for p in parts if p.kind == "CONSECUTIVE"]
    if not limited:
        return parts[0]
    return min(limited, key=lambda p: p.max_consecutive)


def moa_label(moa: Moa) -> str:
    """화면 표기: '가1 (FRAC 4)'. system과 code가 모두 있을 때만 괄호를 붙인다."""
    if moa.system and moa.code:
        return f"{moa.label_kr} ({moa.system} {moa.code})"
    return moa.label_kr
