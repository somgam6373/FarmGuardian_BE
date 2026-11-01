import pytest

from app.catalog.application import catalog_service, label_service
from app.catalog.domain.entities import LabelRead
from app.catalog.infrastructure.integrations import label_reader


def test_all_pesticides_lists_every_drug_once():
    drugs = catalog_service.all_pesticides()

    assert len(drugs) > 1000
    assert len({drug.id for drug in drugs}) == len(drugs)
    for drug in (drugs[0], drugs[len(drugs) // 2], drugs[-1]):
        assert catalog_service.get_pesticide(drug.id) == drug


def _fake_reader(monkeypatch, read):
    monkeypatch.setattr(label_reader, "read_label", lambda image, media_type: read)


def test_scan_label_matches_the_read_against_the_catalog(monkeypatch):
    target = catalog_service.all_pesticides()[0]
    read = LabelRead(target.name, target.item_name, None, "text")
    _fake_reader(monkeypatch, read)

    scan = label_service.scan_label(b"image", "image/jpeg")

    assert scan.candidates[0].pesticide == target
    assert scan.candidates[0].score == 1.0
    assert scan.read is read


def test_nothing_read_gives_no_candidates(monkeypatch):
    read = LabelRead(None, None, None, "")
    _fake_reader(monkeypatch, read)

    scan = label_service.scan_label(b"image", "image/png")

    assert scan.candidates == []
    assert scan.read is read


# 이름이 한 글자 차이인 상표 (계통이 다르다). 읽은 상표가 맨 위, 이웃도 목록에 있어야 한다
SIMILAR_PAIRS = [
    ("보스", "보스카"),
    ("보스카", "보스"),
    ("카브리오", "카브리오팀"),
    ("카브리오팀", "카브리오"),
    ("젠토스타", "젠토스타일"),
    ("젠토스타일", "젠토스타"),
]


@pytest.mark.parametrize("read_brand, neighbour", SIMILAR_PAIRS)
def test_real_catalog_similar_pairs(monkeypatch, read_brand, neighbour):
    _fake_reader(monkeypatch, LabelRead(read_brand, None, None, ""))

    scan = label_service.scan_label(b"image", "image/jpeg")

    names = [candidate.pesticide.name for candidate in scan.candidates]
    assert names[0] == read_brand
    assert neighbour in names
