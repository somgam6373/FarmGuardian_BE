from datetime import timedelta

import pytest

from app.catalog.application import catalog_service as catalog
from app.judgment.domain.schemas import Verdict
from app.spraying.application.spray_service import SprayView
from app.spraying.domain.entities import Spray
from tests.judgment_scenarios import (
    CROPS,
    PLANTED,
    assess,
    pests_with_drugs,
    pool,
    unregistered_drug,
)

NOTICE = "병해충을 지정하면 대안을 볼 수 있습니다"


def history_for(crop_id):
    drugs = [e.pesticide for e in catalog.list_pesticides(crop_id)][:3]
    return [
        SprayView(Spray(i + 1, d.id, PLANTED + timedelta(days=10 * (i + 1)), "manual"), d)
        for i, d in enumerate(drugs)
    ]


def picks(drugs):
    """The first, the middle and the last drug of a pool, without repeats."""
    return list({d.id: d for d in (drugs[0], drugs[len(drugs) // 2], drugs[-1])}.values())


def check(answer, chosen, pest_id, label):
    keys = [c.key for c in answer.result.checks]
    assert keys == ["registration", "timing", "count", "moa"], label
    verdict = answer.result.verdict
    wants_notice = pest_id is None and verdict is Verdict.BLOCKED
    assert (NOTICE in answer.result.notices) == wants_notice, label
    ids = [d.id for d in answer.alternatives]
    assert len(ids) == len(set(ids)) and chosen.id not in ids, label
    assert all(d.moa is not None for d in answer.alternatives), label
    if pest_id is None:
        assert ids == [] and answer.show_extension_office is False, label
        return
    if chosen.moa:
        assert chosen.moa.label_kr not in {d.moa.label_kr for d in answer.alternatives}, label
    order = [(d.moa.label_kr, d.item_name, d.name) for d in answer.alternatives]
    assert order == sorted(order), label
    wants_office = verdict in (Verdict.BLOCKED, Verdict.CAUTION) and not ids
    assert answer.show_extension_office is wants_office, label


@pytest.mark.parametrize("crop_id", CROPS)
def test_every_pest_with_three_of_its_drugs_and_an_unregistered_one(crop_id):
    history = history_for(crop_id)
    for pest_id in pests_with_drugs(crop_id):
        # 등록된 약제 셋과, 등록되지 않은 약제(불가이면서 대안이 없을 수 있는 경우)
        for chosen in [*picks(pool(crop_id, pest_id)), unregistered_drug(crop_id)]:
            label = f"crop {crop_id} pest {pest_id} drug {chosen.id}"
            answer = assess(
                crop_id=crop_id, pest_id=pest_id, pesticide_id=chosen.id, history=history
            )

            check(answer, chosen, pest_id, label)


@pytest.mark.parametrize("crop_id", CROPS)
def test_every_drug_without_a_pest(crop_id):
    history = history_for(crop_id)
    every = {e.pesticide.id: e.pesticide for c in CROPS for e in catalog.list_pesticides(c)}
    for chosen in every.values():
        answer = assess(crop_id=crop_id, pesticide_id=chosen.id, history=history)

        check(answer, chosen, None, f"crop {crop_id} drug {chosen.id}")
