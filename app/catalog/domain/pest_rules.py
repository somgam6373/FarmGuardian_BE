from collections.abc import Mapping, Sequence

OCCURRENCE_SOURCES = {"ncpms": "NCPMS 설명", "pdf": "PDF 경보"}


def format_months(months: Sequence[int]) -> str:
    """발생 월 표기: 연속한 월은 'a~b'로 묶고 마지막에 '월'을 한 번 붙인다."""
    runs: list[list[int]] = []
    for month in sorted(set(months)):
        if runs and month == runs[-1][-1] + 1:
            runs[-1].append(month)
        else:
            runs.append([month])
    return ", ".join(f"{r[0]}~{r[-1]}" if len(r) > 1 else str(r[0]) for r in runs) + "월"


def pick_season(rows: Sequence[Mapping]) -> Mapping | None:
    """근거 문장이 있는 NCPMS 행을 먼저, 없으면 PDF 행을 쓴다."""
    for source in ("ncpms", "pdf"):
        for row in rows:
            if row["source"] == source:
                return row
    return None


def occurrence_text(row: Mapping) -> str:
    """발생 월과 근거. NCPMS는 근거 문장, PDF는 지역·재배형태·등급을 ' · '로 잇는다."""
    if row["source"] == "ncpms":
        basis = row["evidence"]
    else:
        basis = " · ".join(part for part in (row["region"], row["culti"], row["grade"]) if part)
    months = format_months(row["months"])
    return f"{months} — {basis}" if basis else months


def representative_photo(photos: Sequence[Mapping]) -> Mapping | None:
    """대표 사진: is_main이 있으면 그중, 없으면 전체 중 photo_id가 가장 작은 것."""
    if not photos:
        return None
    mains = [photo for photo in photos if photo["is_main"]]
    return min(mains or photos, key=lambda photo: photo["photo_id"])
