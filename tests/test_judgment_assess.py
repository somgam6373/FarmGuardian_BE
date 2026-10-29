from datetime import date, timedelta

import pytest

from app.catalog.application import catalog_service as catalog
from app.catalog.infrastructure.static_data import load
from app.core.errors import AppError
from app.judgment.application import service
from app.judgment.domain.rules import NO_PEST_NOTICE, judge
from app.judgment.domain.schemas import JudgeInput, Moa, Registration, SprayRecord, Verdict
from app.spraying.application.spray_service import SprayView
from app.spraying.domain.entities import Spray
from tests.judgment_scenarios import (
    CROPS,
    PLANTED,
    TODAY,
    assess,
    counting_selection,
    pest_with_alternatives,
    pests_with_drugs,
    pool,
    unregistered_drug,
)

USAGE = {"ok": "NORMAL", "stage": "AT_PLANTING", "no_std": "NO_LIMIT", "failed": "CHECK"}
NOTICE = "병해충을 지정하면 대안을 볼 수 있습니다"


def to_moa(moa):
    return Moa(label_kr=moa.label_kr, system=moa.system, code=moa.code) if moa else None


def raw_registrations(drug, crop_id):
    """Registrations built straight from the raw JSON, independent of the catalog service."""
    std = {s["use_id"]: s for s in load("safe_use_std")}
    pests = {p["pest_id"]: p for p in load("pest")}
    rows = []
    for u in sorted(load("pesticide_use"), key=lambda u: u["use_id"]):
        pest = pests[u["pest_id"]]
        if (u["product"], u["brand"]) != (drug.item_name, drug.name) or pest["crop_id"] != crop_id:
            continue
        s = std[u["use_id"]]
        rows.append(
            Registration(
                pest_id=u["pest_id"],
                pest_name=pest["name"],
                phi_days=s["phi_days"],
                max_uses=s["max_count"],
                use_suittime_raw=u["use_time"],
                use_num_raw=u["use_count"],
                dilut_raw=u["dilution"],
                use_method=u["method"],
                usage_type=USAGE[s["parse_status"]],
                data_asof=date.fromisoformat(s["base_date"]),
            )
        )
    return rows


def expected_result(crop_id, pest_id, drug, history=()):
    return judge(
        JudgeInput(
            today=TODAY,
            planted_at=PLANTED,
            history_confirmed=True,
            pest_id=pest_id,
            pesticide_id=drug.id,
            item_name=drug.item_name,
            moa=to_moa(drug.moa),
            registrations=raw_registrations(drug, crop_id),
            history=list(history),
            psis_asof=date(2026, 10, 5),
        )
    )


SAMPLE = [
    (crop_id, pest_id, drug.id)
    for crop_id in CROPS
    for pest_id in pests_with_drugs(crop_id)[:2]
    for drug in pool(crop_id, pest_id)[:3]
]


@pytest.mark.parametrize("crop_id,pest_id,pesticide_id", SAMPLE)
def test_result_equals_judging_an_independently_built_input(crop_id, pest_id, pesticide_id):
    drug = catalog.get_pesticide(pesticide_id)
    got = assess(crop_id=crop_id, pest_id=pest_id, pesticide_id=pesticide_id).result

    assert got == expected_result(crop_id, pest_id, drug)


def test_history_is_converted_with_item_name_and_moa():
    pest_id, drug = counting_selection()
    spray = Spray(1, drug.id, PLANTED + timedelta(days=10), "manual")
    record = SprayRecord(
        id=1,
        pesticide_id=drug.id,
        item_name=drug.item_name,
        sprayed_on=spray.sprayed_on,
        moa=to_moa(drug.moa),
    )
    got = assess(pesticide_id=drug.id, pest_id=pest_id, history=[SprayView(spray, drug)]).result

    assert got == expected_result(1, pest_id, drug, history=[record])
    assert got.checks[2].facts["used"] == 1


def test_unregistered_drug_without_a_pest_is_blocked_with_the_alternatives_notice():
    answer = assess(pesticide_id=unregistered_drug().id)

    assert answer.result.verdict is Verdict.BLOCKED
    assert answer.result.notices == [NOTICE]
    assert (answer.alternatives, answer.show_extension_office) == ([], False)


def test_registered_drug_without_a_pest_gets_only_the_domain_notice():
    drug = next(
        e.pesticide
        for e in catalog.list_pesticides(1)
        if assess(pesticide_id=e.pesticide.id).result.verdict is Verdict.NEEDS_CHECK
    )
    result = assess(pesticide_id=drug.id).result

    assert result.notices == [NO_PEST_NOTICE]


def test_unregistered_drug_with_a_pest_is_blocked_not_an_error():
    result = assess(pesticide_id=unregistered_drug().id, pest_id=pests_with_drugs(1)[0]).result

    assert result.verdict is Verdict.BLOCKED
    assert result.checks[0].facts == {"crop_registered": False}


def test_unknown_pesticide_is_404():
    with pytest.raises(AppError) as info:
        assess(pesticide_id=999999)

    assert (info.value.status, info.value.code) == (404, "NOT_FOUND")


@pytest.mark.parametrize("pest_id", [999999, pests_with_drugs(2)[0]], ids=["unknown", "other-crop"])
def test_unknown_pest_or_pest_of_another_crop_is_404(pest_id):
    drug = catalog.list_pesticides(1)[0].pesticide
    with pytest.raises(AppError) as info:
        assess(pesticide_id=drug.id, pest_id=pest_id)

    assert (info.value.status, info.value.code) == (404, "NOT_FOUND")


def test_no_alternatives_without_a_pest_even_when_a_pool_exists():
    pest_id = pests_with_drugs(1)[0]
    answer = assess(pesticide_id=pool(1, pest_id)[0].id)

    assert answer.alternatives == []


@pytest.mark.parametrize("pest_id", pests_with_drugs(1)[:4])
def test_alternatives_are_ok_in_another_group_ordered_and_exclude_the_chosen(pest_id):
    for chosen in (unregistered_drug(), pool(1, pest_id)[0]):
        found = assess(pesticide_id=chosen.id, pest_id=pest_id).alternatives
        ids = [d.id for d in found]

        assert len(ids) == len(set(ids)) and chosen.id not in ids
        assert set(ids) <= {d.id for d in pool(1, pest_id)}
        if chosen.moa:
            assert chosen.moa.label_kr not in {d.moa.label_kr for d in found}
        assert found == sorted(found, key=lambda d: (d.moa.label_kr, d.item_name, d.name))
        for alt in found:
            assert assess(pesticide_id=alt.id, pest_id=pest_id).result.verdict is Verdict.OK


@pytest.mark.parametrize("verdict", list(Verdict))
@pytest.mark.parametrize("count", [0, 1])
@pytest.mark.parametrize("pest_given", [False, True])
def test_extension_office_truth_table(pest_given, count, verdict):
    expected = pest_given and count == 0 and verdict in (Verdict.BLOCKED, Verdict.CAUTION)

    assert service.show_extension_office(pest_given, verdict, count) is expected


def test_unconfirmed_history_leaves_no_alternatives_and_asks_the_office():
    answer = assess(
        pesticide_id=unregistered_drug().id,
        pest_id=pests_with_drugs(1)[0],
        history_confirmed=False,
    )

    assert answer.result.verdict is Verdict.BLOCKED
    assert (answer.alternatives, answer.show_extension_office) == ([], True)


def test_confirmed_history_gives_alternatives_and_no_office_for_a_blocked_drug():
    answer = assess(pesticide_id=unregistered_drug().id, pest_id=pest_with_alternatives())

    assert answer.result.verdict is Verdict.BLOCKED
    assert answer.alternatives and answer.show_extension_office is False


def test_needs_check_verdict_never_asks_the_office():
    pest_id = pests_with_drugs(1)[0]
    answer = assess(pesticide_id=pool(1, pest_id)[0].id, pest_id=pest_id, history_confirmed=False)

    assert answer.result.verdict is Verdict.NEEDS_CHECK
    assert (answer.alternatives, answer.show_extension_office) == ([], False)


def test_assess_is_repeatable():
    pest_id = pests_with_drugs(1)[0]
    chosen = pool(1, pest_id)[0].id
    first = assess(pesticide_id=chosen, pest_id=pest_id)
    second = assess(pesticide_id=chosen, pest_id=pest_id)

    assert first == second
