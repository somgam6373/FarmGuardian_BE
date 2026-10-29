import pytest

from app.catalog.domain.pest_rules import (
    OCCURRENCE_SOURCES,
    format_months,
    occurrence_text,
    pick_season,
    representative_photo,
)


@pytest.mark.parametrize(
    "months,text",
    [
        ([4, 5, 6, 7], "4~7월"),
        ([6, 8, 9], "6, 8~9월"),
        ([6], "6월"),
        ([6, 7], "6~7월"),
        ([9, 6, 8], "6, 8~9월"),
        ([1, 2, 3, 12], "1~3, 12월"),
        ([6, 6, 7], "6~7월"),
        ([10, 11, 12], "10~12월"),
    ],
)
def test_format_months(months, text):
    assert format_months(months) == text


def season(source, months, **kw):
    base = {
        "source": source,
        "months": months,
        "region": None,
        "culti": None,
        "grade": None,
        "evidence": None,
    }
    return {**base, **kw}


def test_occurrence_text_ncpms_uses_the_evidence_sentence():
    row = season("ncpms", [4, 5, 6, 7], evidence="유충은 4월경에 부화한다")

    assert occurrence_text(row) == "4~7월 — 유충은 4월경에 부화한다"


def test_occurrence_text_ncpms_without_evidence_is_months_only():
    assert occurrence_text(season("ncpms", [4, 5])) == "4~5월"


def test_occurrence_text_pdf_joins_region_culti_and_grade():
    row = season("pdf", [6, 7], region="대관령", culti="고랭지, 씨감자", grade="예보")

    assert occurrence_text(row) == "6~7월 — 대관령 · 고랭지, 씨감자 · 예보"


def test_occurrence_text_pdf_skips_missing_parts():
    assert occurrence_text(season("pdf", [8, 9], grade="주의보")) == "8~9월 — 주의보"
    assert occurrence_text(season("pdf", [8, 9])) == "8~9월"


def test_occurrence_sources():
    assert OCCURRENCE_SOURCES == {"ncpms": "NCPMS 설명", "pdf": "PDF 경보"}


def test_pick_season_prefers_ncpms_then_pdf_then_none():
    ncpms, pdf = season("ncpms", [6]), season("pdf", [7])

    assert pick_season([pdf, ncpms]) is ncpms
    assert pick_season([pdf]) is pdf
    assert pick_season([ncpms]) is ncpms
    assert pick_season([]) is None


def photo(photo_id, is_main=False):
    return {"photo_id": photo_id, "is_main": is_main, "url": f"u{photo_id}"}


def test_representative_photo_falls_back_to_the_lowest_photo_id():
    assert representative_photo([photo(3), photo(1), photo(2)])["photo_id"] == 1


def test_representative_photo_prefers_the_main_one_even_when_not_first():
    assert representative_photo([photo(1), photo(5, True), photo(2)])["photo_id"] == 5


def test_representative_photo_with_several_mains_takes_the_lowest_id():
    assert representative_photo([photo(7, True), photo(4, True), photo(1)])["photo_id"] == 4


def test_representative_photo_single_and_empty():
    assert representative_photo([photo(9)])["photo_id"] == 9
    assert representative_photo([]) is None
