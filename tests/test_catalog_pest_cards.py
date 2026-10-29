from app.catalog.application import catalog_service as svc
from app.catalog.infrastructure.static_data import load


def raw(name):
    return load(name)


def season_of(pest_id, source):
    return next(
        s for s in raw("pest_season") if s["pest_id"] == pest_id and s["source"] == source
    )


def test_unknown_pest_is_none():
    assert svc.get_pest_card(999999) is None


def test_kind_is_mapped():
    assert svc.get_pest_card(8).kind == "병"
    assert svc.get_pest_card(48).kind == "해충"


def test_description_is_the_symptom_or_none():
    pest = next(p for p in raw("pest") if p["pest_id"] == 8)

    assert svc.get_pest_card(8).description == pest["symptom"]
    assert svc.get_pest_card(122).description is None


def test_photo_comes_from_the_pests_own_photos_and_crop():
    for pest in raw("pest"):
        card = svc.get_pest_card(pest["pest_id"])
        own = [p for p in raw("pest_photo") if p["pest_id"] == pest["pest_id"]]
        if own:
            assert card.photo_url == min(own, key=lambda p: p["photo_id"])["url"]
            assert card.photo_source == pest["photo_crop"]
        else:
            assert (card.photo_url, card.photo_source) == (None, None)


def test_pest_without_photo_has_null_photo_fields():
    card = svc.get_pest_card(24)

    assert (card.photo_url, card.photo_source) == (None, None)


def test_occurrence_from_a_pdf_row():
    card = svc.get_pest_card(8)

    assert card.occurrence == "6~7월 — 대관령 · 고랭지, 씨감자 · 예보"
    assert card.occurrence_source == "PDF 경보"


def test_occurrence_from_an_ncpms_row():
    card = svc.get_pest_card(101)

    assert card.occurrence == "4~7월 — " + season_of(101, "ncpms")["evidence"]
    assert card.occurrence_source == "NCPMS 설명"


def test_two_row_pests_use_the_ncpms_row():
    first, second = svc.get_pest_card(48), svc.get_pest_card(50)

    assert first.occurrence == "6, 8~9월 — " + season_of(48, "ncpms")["evidence"]
    assert second.occurrence == "4~6월 — " + season_of(50, "ncpms")["evidence"]
    assert (first.occurrence_source, second.occurrence_source) == ("NCPMS 설명", "NCPMS 설명")


def test_pest_without_season_has_null_occurrence():
    card = svc.get_pest_card(1)

    assert (card.occurrence, card.occurrence_source) == (None, None)


def test_virus_card_lists_its_vectors_by_name():
    card = svc.get_pest_card(66)
    row = next(
        v
        for v in raw("virus_vector")
        if v["virus_pest_id"] == 66 and v["vector_pest_id"] == 90
    )

    assert [(v.id, v.name) for v in card.vectors] == [
        (87, "꽃노랑총채벌레"),
        (90, "대만총채벌레"),
        (115, "오이총채벌레"),
    ]
    assert card.vectors[1].guide == row["guide_text"]
    assert card.vectors[1].source == row["evidence"]


def test_virus_without_a_vector_pest_has_no_vectors():
    assert svc.get_pest_card(64).vectors == ()


def test_non_virus_has_no_vectors():
    assert svc.get_pest_card(1).vectors == ()


def test_all_129_cards_build_with_the_expected_totals():
    cards = [svc.get_pest_card(p["pest_id"]) for p in raw("pest")]

    assert len(cards) == 129
    assert sum(c.photo_url is not None for c in cards) == 102
    assert sum(c.occurrence is not None for c in cards) == 49
    assert sum(bool(c.vectors) for c in cards) == 5
