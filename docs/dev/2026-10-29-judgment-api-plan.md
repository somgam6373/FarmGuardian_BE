# Judgment API Implementation Plan (BE-45)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (project CLAUDE.md: no subagent-driven execution). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `POST /zones/{id}/judgments` in the shape of the API spec §7: judge one pesticide (optionally against one pest) for a zone with the finished pure domain, add the notices, alternatives and `show_extension_office`, save the judgment, answer 201 `JudgeResponse`.

**Architecture:** `judgment/application/service.py` holds a DB-free `assess()` (catalog rows + zone context + history → `JudgeInput` → `judge()` → service additions) and `run_judgment()` (reads, assesses, saves). Inputs come from small functions of other contexts: `catalog_service.get_registrations`/`data_asof`, `spray_service.history`, `farm.application.zone_reader.get_zone_context`. A repository in `judgment/infrastructure` inserts the `judgment` row.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2 `text()` SQL on psycopg 3, Pydantic v2 (the domain models are Pydantic), pytest against the PostGIS test database.

**Spec:** `docs/dev/2026-10-29-judgment-api-design.md` (approved in chat 2026-10-29); frame = `docs/dev/팜가디언_API_명세.md` §7 (never edited).

## Global Constraints

- `팜가디언_API_명세.md` is the frame and **must not change**; `schema.sql` does not change either. `judgment/domain/` is not edited.
- Response `JudgeResponse` = exactly `{judgment_id, apply_date, result, alternatives, show_extension_office}`; `result` = the domain `JudgeResult` (`pesticide_id, moa, verdict, checks, notices, data_asof`, 4 checks in the order registration, timing, count, moa); an alternative = `{id, name, item_name, moa}` (the shape of `PesticideBase`). Status 201.
- Validation order: zone (404, `get_owned_zone`, wins over the body) → body shape (422) → `apply_date` after 2100-12-31 (422, `loc` `["body","apply_date"]`, value not echoed) → pesticide (404) → pest (404: unknown, or a pest of another crop; via `catalog_service.list_pesticides(crop_id, pest_id)`). A 404 or 422 stores nothing.
- `apply_date` default = `today_kst()`; it is only the domain's `today`. The zone's whole spray history is used whatever `apply_date` is.
- A pesticide not registered for the zone's crop or pest is not an error (① is `BLOCKED`).
- Service additions: no pest and verdict `BLOCKED` → append the notice 「병해충을 지정하면 대안을 볼 수 있습니다」 to the domain's notices; alternatives only with a pest (pool = `list_pesticides(crop_id, pest_id)` minus the chosen drug, each judged with the same zone, history, `today`, pest and its own registrations, then `pick_alternatives`, ordered by `moa.label_kr`, `item_name`, `name`); `show_extension_office` = pest given and verdict `BLOCKED`/`CAUTION` and no alternatives.
- Stored row: `judgment(zone_id, pest_id, pesticide_id, apply_date, verdict, result jsonb)` with `result` = the `JudgeResult` JSON. One row per successful call. The judgment never writes spray records.
- `usage_type` from `parse_status`: ok → NORMAL, stage → AT_PLANTING, no_std → NO_LIMIT, failed → CHECK (mapping lives in the judgment service); `Registration.data_asof` = `safe_use_std.base_date`; `psis_asof` = `catalog_service.data_asof()`.
- Layers: `domain` untouched; `presentation` calls only `application`; other contexts are used through their `application` functions (the catalog `PesticideBase` schema is reused for alternatives, as in `spraying`).
- Code and identifiers in English, short Korean comments as in `app/core`; ruff line length 100 (Korean characters count double, wrap long strings); tests flat in `tests/`; commit messages in English; do not push; stage explicit paths only (the working tree has an unrelated uncommitted backlog xlsx and `.gitignore` change).

## Review Focus

- `apply_date` near the end of the date range must not be a 500: 2101-01-01 is 422, 2100-12-31 works with the domain's `today + phi_days`. (Task 5)
- An unregistered drug is a normal `BLOCKED` answer, with the unspecified-pest notice only when no pest was given. (Tasks 3, 5)
- A pest of another crop, an unknown pest and an unknown pesticide are 404 and leave no `judgment` row. (Task 5)
- The history is used whole whatever `apply_date` is, and the judgment never creates spray records. (Task 5)
- Alternatives are `OK` when judged on their own, have another action group, exclude the chosen drug, and come in the documented order; none without a pest. (Tasks 3, 4)
- The service's mapping of static rows equals an independent build from the raw JSON. (Task 3)

---

### Task 0: Commit the design and this plan

- [ ] **Step 1:** `git add docs/dev/2026-10-29-judgment-api-design.md docs/dev/2026-10-29-judgment-api-plan.md` / `git commit -m "Add judgment API design and plan"` (stage only these two files).

### Task 1: Catalog registration rows and data date

**Files:**
- Modify: `app/catalog/domain/entities.py`, `app/catalog/application/catalog_service.py`
- Test: `tests/test_catalog_registrations.py`

**Interfaces:**
- Produces in `entities.py` (frozen dataclass): `UseRow(pest_id: int, pest_name: str, phi_days: int | None, max_uses: int | None, use_time: str | None, use_count: str | None, dilution: str | None, method: str | None, parse_status: str, base_date: date)`.
- Produces in `catalog_service.py`: `get_registrations(pesticide_id: int, crop_id: int) -> list[UseRow]` (every `pesticide_use` row of that drug for the crop, joined to its `safe_use_std` row by `use_id`, ordered by `use_id`; `[]` for an unknown drug or crop); `data_asof() -> date` (the `base_date` of the static data). The row index is built once (`functools.cache`); a drug is the (`product`, `brand`) pair of the existing `_drugs()` (`Pesticide.item_name` = product, `Pesticide.name` = brand).

- [ ] **Step 1: Write the failing tests** in `tests/test_catalog_registrations.py`
```python
from datetime import date

from app.catalog.application import catalog_service as svc
from app.catalog.infrastructure.static_data import load


def all_drugs():
    return {
        e.pesticide.id: e.pesticide for crop_id in (1, 2, 3) for e in svc.list_pesticides(crop_id)
    }


def as_tuple(row):
    return (
        row.pest_id,
        row.pest_name,
        row.phi_days,
        row.max_uses,
        row.use_time,
        row.use_count,
        row.dilution,
        row.method,
        row.parse_status,
        row.base_date,
    )


def raw_index():
    """Independent join of the raw JSON: (product, brand, crop) -> rows by use_id."""
    std = {s["use_id"]: s for s in load("safe_use_std")}
    pests = {p["pest_id"]: p for p in load("pest")}
    index = {}
    for u in sorted(load("pesticide_use"), key=lambda u: u["use_id"]):
        s, pest = std[u["use_id"]], pests[u["pest_id"]]
        row = (
            u["pest_id"],
            pest["name"],
            s["phi_days"],
            s["max_count"],
            u["use_time"],
            u["use_count"],
            u["dilution"],
            u["method"],
            s["parse_status"],
            date.fromisoformat(s["base_date"]),
        )
        index.setdefault((u["product"], u["brand"], pest["crop_id"]), []).append(row)
    return index


def test_rows_match_an_independent_join_for_every_drug_and_crop():
    index = raw_index()
    for drug in all_drugs().values():
        for crop_id in (1, 2, 3):
            expected = index.get((drug.item_name, drug.name, crop_id), [])

            assert [as_tuple(r) for r in svc.get_registrations(drug.id, crop_id)] == expected


def test_every_pesticide_use_row_is_returned_exactly_once():
    total = sum(
        len(svc.get_registrations(drug.id, crop_id))
        for drug in all_drugs().values()
        for crop_id in (1, 2, 3)
    )

    assert total == len(load("pesticide_use")) == 4133


def test_unknown_drug_or_crop_has_no_rows():
    drug = next(iter(all_drugs().values()))

    assert svc.get_registrations(999999, 1) == []
    assert svc.get_registrations(drug.id, 99) == []


def test_data_asof_is_the_static_base_date():
    assert svc.data_asof() == date(2026, 10, 5)
```
- [ ] **Step 2: Run** `.venv\Scripts\python -m pytest tests\test_catalog_registrations.py -q` — Expected: FAIL (`get_registrations` / `data_asof` missing).
- [ ] **Step 3: Implement** `UseRow`, `get_registrations` and `data_asof` per the interface block.
- [ ] **Step 4: Run** the step 2 command — Expected: `4 passed`. Whole suite and `ruff check .` clean.
- [ ] **Step 5: Commit** `git add app/catalog tests/test_catalog_registrations.py` / `git commit -m "Add catalog registration rows"`

### Task 2: Spray history and zone reader

**Files:**
- Modify: `app/spraying/infrastructure/repository.py`, `app/spraying/application/spray_service.py`
- Create: `app/farm/application/zone_reader.py`
- Test: `tests/test_spray_history.py`, `tests/test_zone_reader.py`

**Interfaces:**
- Produces in `repository.py`: `all_for_zone(db: Session, zone_id: int) -> list[Spray]` (all records, `sprayed_on` DESC then `id` DESC).
- Produces in `spray_service.py`: `history(db: Session, zone_id: int) -> list[SprayView]` (all records of the zone, same order, pesticide resolved; not paged).
- Produces in `zone_reader.py`: `ZoneContext(crop_id: int, planted_at: date | None, history_confirmed: bool)` (frozen dataclass) and `get_zone_context(db: Session, zone_id: int) -> ZoneContext` (`text()` SQL on `zone`; `AppError("NOT_FOUND", 404, ...)` when the zone does not exist).

- [ ] **Step 1: Write the failing tests**

`tests/test_spray_history.py`
```python
import uuid
from datetime import date, timedelta

import pytest

from app.catalog.application import catalog_service as catalog
from app.spraying.application import spray_service as svc

TODAY = date(2026, 10, 29)
A, B = [e.pesticide.id for e in catalog.list_pesticides(1)[:2]]


@pytest.fixture
def zones(make_user, make_field, make_zone):
    uid = make_user("farmer")
    field = make_field(uid)
    return make_zone(field, uid), make_zone(field, uid)


def record(db, zone, pesticide_id=A, sprayed_on=TODAY):
    return svc.record_spray(
        db,
        zone,
        pesticide_id=pesticide_id,
        sprayed_on=sprayed_on,
        source="manual",
        request_id=uuid.uuid4(),
        allow_duplicate=True,
        today=TODAY,
    )[0]


def test_history_is_newest_first_with_the_pesticide_resolved(db, zones):
    old = record(db, zones[0], A, TODAY - timedelta(days=9))
    first = record(db, zones[0], A, TODAY)
    second = record(db, zones[0], B, TODAY)
    views = svc.history(db, zones[0])

    assert [v.spray.id for v in views] == [second.spray.id, first.spray.id, old.spray.id]
    assert [v.pesticide for v in views] == [catalog.get_pesticide(p) for p in (B, A, A)]


def test_history_is_not_paged(db, zones):
    for day in range(25):
        record(db, zones[0], A, TODAY - timedelta(days=day))

    assert len(svc.history(db, zones[0])) == 25 > 20


def test_history_excludes_other_zones_and_is_empty_for_a_new_zone(db, zones):
    record(db, zones[1])

    assert svc.history(db, zones[0]) == []
    assert len(svc.history(db, zones[1])) == 1
```
`tests/test_zone_reader.py`
```python
from datetime import date

import pytest
from sqlalchemy import text

from app.core.errors import AppError
from app.farm.application import zone_reader


def test_reads_crop_planting_date_and_confirmation(db, make_user, make_field, make_zone):
    uid = make_user("farmer")
    zone = make_zone(make_field(uid), uid)
    first_crop = db.scalar(text("SELECT min(id) FROM crop"))

    context = zone_reader.get_zone_context(db, zone)
    assert (context.crop_id, context.planted_at, context.history_confirmed) == (
        first_crop,
        None,
        False,
    )

    db.execute(
        text(
            "UPDATE zone SET crop_id = 3, planted_at = '2026-04-01', "
            "history_confirmed = true WHERE id = :id"
        ),
        {"id": zone},
    )
    context = zone_reader.get_zone_context(db, zone)

    assert (context.crop_id, context.planted_at, context.history_confirmed) == (
        3,
        date(2026, 4, 1),
        True,
    )


def test_unknown_zone_is_404(db):
    with pytest.raises(AppError) as info:
        zone_reader.get_zone_context(db, 999999)

    assert (info.value.status, info.value.code) == (404, "NOT_FOUND")
```
- [ ] **Step 2: Run** `.venv\Scripts\python -m pytest tests\test_spray_history.py tests\test_zone_reader.py -q` — Expected: FAIL (`history` missing; `No module named 'app.farm.application.zone_reader'`).
- [ ] **Step 3: Implement** `all_for_zone`, `history` and `zone_reader` per the interface block (`history` resolves each record like `list_sprays` does).
- [ ] **Step 4: Run** the step 2 command — Expected: `5 passed`. Whole suite and `ruff check .` clean.
- [ ] **Step 5: Commit** `git add app/spraying app/farm/application/zone_reader.py tests/test_spray_history.py tests/test_zone_reader.py` / `git commit -m "Add spray history and zone reader"`

### Task 3: The judgment `assess` function

**Files:**
- Create: `app/judgment/application/__init__.py`, `app/judgment/application/service.py`, `tests/judgment_scenarios.py`
- Test: `tests/test_judgment_assess.py`

**Interfaces:**
- Consumes: `catalog_service.get_pesticide`, `list_pesticides`, `get_registrations`, `data_asof` (Task 1), `SprayView` (spraying), the domain `judge`, `pick_alternatives`, schemas.
- Produces in `service.py`: `Assessment(result: JudgeResult, alternatives: list[Pesticide], show_extension_office: bool)` (frozen dataclass; `Pesticide` is the catalog entity); `show_extension_office(pest_given: bool, verdict: Verdict, alternative_count: int) -> bool`; `assess(*, crop_id: int, planted_at: date | None, history_confirmed: bool, history: Sequence[SprayView], pesticide_id: int, pest_id: int | None, today: date) -> Assessment`; constant `NO_ALTERNATIVE_NOTICE = "병해충을 지정하면 대안을 볼 수 있습니다"`. `assess` raises `AppError("NOT_FOUND", 404, ...)` for an unknown pesticide, then for an unknown pest or a pest of another crop (through `list_pesticides`). It builds each `Registration` from a `UseRow` (private helper), each `SprayRecord` from a history view (`item_name`/`moa` of its pesticide) and converts the catalog `Moa` to the domain `Moa`.
- Produces in `tests/judgment_scenarios.py` (not a test module; shared by Tasks 3-5): `CROPS`, `TODAY = date(2026, 10, 29)`, `PLANTED = date(2026, 4, 1)`, `pool(crop_id, pest_id) -> list[Pesticide]`, `pests_with_drugs(crop_id) -> list[int]` (cached), `unregistered_drug(crop_id=1) -> Pesticide` (a drug with no registration row for the crop, cached), `assess(**overrides)` (a call of `service.assess` with defaults crop 1, `PLANTED`, history confirmed, empty history, `TODAY`), `pest_with_alternatives(crop_id=1) -> int` (cached: the first pest where `unregistered_drug` has alternatives in the confirmed context), `counting_selection(crop_id=1) -> tuple[int, Pesticide]` (cached: the first (pest, drug) whose considered rows are all `ok` with `max_uses >= 2`).

- [ ] **Step 1: Write the failing tests**

`tests/judgment_scenarios.py`
```python
from datetime import date
from functools import cache

from app.catalog.application import catalog_service as catalog
from app.catalog.infrastructure.static_data import load
from app.judgment.application import service

CROPS = (1, 2, 3)
TODAY = date(2026, 10, 29)
PLANTED = date(2026, 4, 1)


def pool(crop_id, pest_id):
    return [e.pesticide for e in catalog.list_pesticides(crop_id, pest_id)]


@cache
def pests_with_drugs(crop_id):
    return [
        p["pest_id"] for p in load("pest") if p["crop_id"] == crop_id and pool(crop_id, p["pest_id"])
    ]


@cache
def unregistered_drug(crop_id=1):
    every = {e.pesticide.id: e.pesticide for c in CROPS for e in catalog.list_pesticides(c)}
    return next(d for d in every.values() if not catalog.get_registrations(d.id, crop_id))


def assess(**overrides):
    args = {
        "crop_id": 1,
        "planted_at": PLANTED,
        "history_confirmed": True,
        "history": [],
        "pesticide_id": None,
        "pest_id": None,
        "today": TODAY,
    }
    return service.assess(**{**args, **overrides})


@cache
def pest_with_alternatives(crop_id=1):
    chosen = unregistered_drug(crop_id)
    for pest_id in pests_with_drugs(crop_id):
        if assess(crop_id=crop_id, pesticide_id=chosen.id, pest_id=pest_id).alternatives:
            return pest_id
    raise LookupError("no pest with alternatives")


@cache
def counting_selection(crop_id=1):
    for pest_id in pests_with_drugs(crop_id):
        for drug in pool(crop_id, pest_id):
            rows = [r for r in catalog.get_registrations(drug.id, crop_id) if r.pest_id == pest_id]
            if rows and all(r.parse_status == "ok" and (r.max_uses or 0) >= 2 for r in rows):
                return pest_id, drug
    raise LookupError("no counting selection")
```
`tests/test_judgment_assess.py`
```python
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
    result = assess(pesticide_id=unregistered_drug().id)

    assert result.result.verdict is Verdict.BLOCKED
    assert result.result.notices == [NOTICE]
    assert (result.alternatives, result.show_extension_office) == ([], False)


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
    result = assess(pesticide_id=pool(1, pest_id)[0].id)

    assert result.alternatives == []


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
    result = assess(
        pesticide_id=unregistered_drug().id,
        pest_id=pests_with_drugs(1)[0],
        history_confirmed=False,
    )

    assert result.result.verdict is Verdict.BLOCKED
    assert (result.alternatives, result.show_extension_office) == ([], True)


def test_confirmed_history_gives_alternatives_and_no_office_for_a_blocked_drug():
    result = assess(pesticide_id=unregistered_drug().id, pest_id=pest_with_alternatives())

    assert result.result.verdict is Verdict.BLOCKED
    assert result.alternatives and result.show_extension_office is False


def test_needs_check_verdict_never_asks_the_office():
    pest_id = pests_with_drugs(1)[0]
    result = assess(
        pesticide_id=pool(1, pest_id)[0].id, pest_id=pest_id, history_confirmed=False
    )

    assert result.result.verdict is Verdict.NEEDS_CHECK
    assert (result.alternatives, result.show_extension_office) == ([], False)


def test_assess_is_repeatable():
    pest_id = pests_with_drugs(1)[0]
    chosen = pool(1, pest_id)[0].id

    first = assess(pesticide_id=chosen, pest_id=pest_id)
    second = assess(pesticide_id=chosen, pest_id=pest_id)

    assert first == second
```
- [ ] **Step 2: Run** `.venv\Scripts\python -m pytest tests\test_judgment_assess.py -q` — Expected: collection ERROR (`No module named 'app.judgment.application'`).
- [ ] **Step 3: Implement** `service.py` per the interface block and Global Constraints (call the domain through `judge` and `pick_alternatives`; add the notice with `result.model_copy(update=...)`; sort alternatives by `(moa.label_kr, item_name, name)`).
- [ ] **Step 4: Run** the step 2 command — Expected: all pass, 0 skipped (the sampled oracle has one case per sampled selection, so the total depends on the data; write the printed count in the ledger). Whole suite and `ruff check .` clean. If the file is slow, report the time in the ledger.
- [ ] **Step 5: Commit** `git add app/judgment/application tests/judgment_scenarios.py tests/test_judgment_assess.py` / `git commit -m "Add judgment assessment"`

### Task 4: Real-data sweep

**Files:**
- Test: `tests/test_judgment_sweep.py`

**Interfaces:**
- Consumes: `assess` and the scenario helpers (Task 3). No production code.

- [ ] **Step 1: Write the test** in `tests/test_judgment_sweep.py`
```python
from datetime import timedelta

import pytest

from app.catalog.application import catalog_service as catalog
from app.judgment.domain.schemas import Verdict
from app.spraying.application.spray_service import SprayView
from app.spraying.domain.entities import Spray
from tests.judgment_scenarios import CROPS, PLANTED, assess, pests_with_drugs, pool

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
    assert [c.key for c in answer.result.checks] == ["registration", "timing", "count", "moa"], label
    verdict = answer.result.verdict
    assert (NOTICE in answer.result.notices) == (pest_id is None and verdict is Verdict.BLOCKED), label
    ids = [d.id for d in answer.alternatives]
    assert len(ids) == len(set(ids)) and chosen.id not in ids, label
    assert all(d.moa is not None for d in answer.alternatives), label
    if pest_id is None:
        assert ids == [] and answer.show_extension_office is False, label
        return
    if chosen.moa:
        assert chosen.moa.label_kr not in {d.moa.label_kr for d in answer.alternatives}, label
    keys = [(d.moa.label_kr, d.item_name, d.name) for d in answer.alternatives]
    assert keys == sorted(keys), label
    wants_office = verdict in (Verdict.BLOCKED, Verdict.CAUTION) and not ids
    assert answer.show_extension_office is wants_office, label


@pytest.mark.parametrize("crop_id", CROPS)
def test_every_pest_with_three_of_its_drugs(crop_id):
    history = history_for(crop_id)
    for pest_id in pests_with_drugs(crop_id):
        for chosen in picks(pool(crop_id, pest_id)):
            label = f"crop {crop_id} pest {pest_id} drug {chosen.id}"
            answer = assess(crop_id=crop_id, pest_id=pest_id, pesticide_id=chosen.id, history=history)

            check(answer, chosen, pest_id, label)


@pytest.mark.parametrize("crop_id", CROPS)
def test_every_drug_without_a_pest(crop_id):
    history = history_for(crop_id)
    every = {e.pesticide.id: e.pesticide for c in CROPS for e in catalog.list_pesticides(c)}
    for chosen in every.values():
        answer = assess(crop_id=crop_id, pesticide_id=chosen.id, history=history)

        check(answer, chosen, None, f"crop {crop_id} drug {chosen.id}")
```
- [ ] **Step 2: Run** `.venv\Scripts\python -m pytest tests\test_judgment_sweep.py -q --durations=3` — Expected: `6 passed`; note the time. If the file takes longer than about 20 s, narrow the drugs per pest to the first and last and say so in the ledger.
- [ ] **Step 3: Run once, not committed:** an exhaustive sweep script in the scratchpad (every (crop, pest, drug) selection with a pest, and every (crop, drug) without one, with an empty and with the three-spray history) reporting the selection counts, the number with alternatives and with no alternative, the verdict distribution and the total time. Ledger the numbers.
- [ ] **Step 4:** Whole suite and `ruff check .` clean.
- [ ] **Step 5: Commit** `git add tests/test_judgment_sweep.py` / `git commit -m "Add judgment sweep over the real catalog"`

### Task 5: Persistence and the endpoint

**Files:**
- Create: `app/judgment/infrastructure/__init__.py`, `app/judgment/infrastructure/repository.py`, `app/judgment/presentation/__init__.py`, `app/judgment/presentation/schemas.py`, `app/judgment/presentation/router.py`
- Modify: `app/judgment/application/service.py`, `app/main.py`
- Test: `tests/test_judgment_api.py`

**Interfaces:**
- Consumes: `assess` (Task 3), `spray_service.history`, `zone_reader.get_zone_context` (Task 2), `get_owned_zone`, `get_db`, `today_kst`, `pesticide_base`.
- Produces in `repository.py`: `insert(db, zone_id: int, pest_id: int | None, pesticide_id: int, apply_date: date, verdict: str, result_json: str) -> int` (`INSERT ... CAST(:result AS jsonb) ... RETURNING id`, no commit).
- Produces in `service.py`: `Judgment(id: int, apply_date: date, assessment: Assessment)` (frozen dataclass); `run_judgment(db, zone_id: int, *, pesticide_id: int, pest_id: int | None, apply_date: date | None, today: date) -> Judgment`: `apply_date` after `date(2100, 12, 31)` raises `AppError("VALIDATION_ERROR", 422, <message>, {"errors": [{"loc": ["body","apply_date"], "msg": <message>, "type": "value_error"}]})` before any read; reads the zone context and the history; `assess(... today=apply_date or today)`; inserts the row (`verdict.value`, `result.model_dump_json()`); commits; returns the `Judgment`.
- Produces in `schemas.py`: `JudgmentIn(pesticide_id: int, pest_id: int | None = None, apply_date: date | None = None)`; `JudgeResponse(judgment_id: int, apply_date: date, result: JudgeResult, alternatives: list[PesticideBase], show_extension_office: bool)`.
- Produces in `router.py`: `router = APIRouter(dependencies=[Depends(current_user)])` with `POST /zones/{zone_id}/judgments` (`status_code=201`, zone from `Depends(get_owned_zone)`, `today=today_kst()`), registered in `app/main.py`.

- [ ] **Step 1: Write the failing tests** in `tests/test_judgment_api.py`
```python
import uuid

import pytest
from sqlalchemy import text

from app.core.time import today_kst
from tests.judgment_scenarios import (
    PLANTED,
    TODAY,
    counting_selection,
    pest_with_alternatives,
    pests_with_drugs,
    pool,
    unregistered_drug,
)

RESPONSE_KEYS = {"judgment_id", "apply_date", "result", "alternatives", "show_extension_office"}
RESULT_KEYS = {"pesticide_id", "moa", "verdict", "checks", "notices", "data_asof"}
CHECK_KEYS = {"key", "status", "message", "facts", "evidence"}
ALT_KEYS = {"id", "name", "item_name", "moa"}
NOTICE = "병해충을 지정하면 대안을 볼 수 있습니다"
PEST = pests_with_drugs(1)[0]
DRUG = pool(1, PEST)[0]


def auth(uid):
    return {"X-User-Id": str(uid)}


@pytest.fixture
def farm(make_user, make_field, make_zone):
    uid = make_user("farmer")
    return uid, make_zone(make_field(uid), uid)


def confirm(db, zone):
    db.execute(
        text("UPDATE zone SET planted_at = :p, history_confirmed = true WHERE id = :id"),
        {"p": PLANTED, "id": zone},
    )


def judge(client, uid, zone, **body):
    return client.post(f"/zones/{zone}/judgments", json=body, headers=auth(uid))


def stored(db, zone):
    return db.execute(
        text(
            "SELECT id, pest_id, pesticide_id, apply_date, verdict, result "
            "FROM judgment WHERE zone_id = :z ORDER BY id"
        ),
        {"z": zone},
    ).all()


def test_requires_authentication(client):
    r = client.post("/zones/1/judgments", json={})

    assert (r.status_code, r.json()["error"]["code"]) == (401, "UNAUTHORIZED")


def test_foreign_and_unknown_zones_are_404(client, make_user, make_field, make_zone, farm):
    uid, _ = farm
    other = make_user("other")
    foreign = make_zone(make_field(other), other)
    for zone in (foreign, 999999):
        r = client.post(f"/zones/{zone}/judgments", json={}, headers=auth(uid))  # 404 beats 422

        assert (r.status_code, r.json()["error"]["code"]) == (404, "NOT_FOUND")


def test_unknown_pesticide_is_404_and_stores_nothing(client, db, farm):
    uid, zone = farm
    r = judge(client, uid, zone, pesticide_id=999999)

    assert (r.status_code, r.json()["error"]["code"]) == (404, "NOT_FOUND")
    assert stored(db, zone) == []


@pytest.mark.parametrize("pest_id", [999999, pests_with_drugs(2)[0]], ids=["unknown", "other-crop"])
def test_unknown_pest_or_pest_of_another_crop_is_404_and_stores_nothing(client, db, farm, pest_id):
    uid, zone = farm
    r = judge(client, uid, zone, pesticide_id=DRUG.id, pest_id=pest_id)

    assert (r.status_code, r.json()["error"]["code"]) == (404, "NOT_FOUND")
    assert stored(db, zone) == []


def test_apply_date_after_2100_is_422_but_the_last_day_of_2100_is_accepted(client, db, farm):
    uid, zone = farm
    r = judge(client, uid, zone, pesticide_id=DRUG.id, apply_date="2101-01-01")
    error = r.json()["error"]

    assert (r.status_code, error["code"]) == (422, "VALIDATION_ERROR")
    assert error["details"]["errors"][0]["loc"] == ["body", "apply_date"]
    assert "2101" not in str(error)
    assert stored(db, zone) == []
    accepted = judge(client, uid, zone, pesticide_id=DRUG.id, apply_date="2100-12-31")
    assert (accepted.status_code, accepted.json()["apply_date"]) == (201, "2100-12-31")


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"pesticide_id": "x"},
        {"pesticide_id": 1, "pest_id": "x"},
        {"pesticide_id": 1, "apply_date": "nope"},
    ],
    ids=["empty", "pesticide-type", "pest-type", "date-type"],
)
def test_malformed_bodies_are_422_and_store_nothing(client, db, farm, body):
    uid, zone = farm
    r = judge(client, uid, zone, **body)

    assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_ERROR")
    assert stored(db, zone) == []


def test_response_has_exactly_the_spec_shape(client, db, farm):
    uid, zone = farm
    confirm(db, zone)
    r = judge(client, uid, zone, pesticide_id=DRUG.id, pest_id=PEST, apply_date=TODAY.isoformat())
    body = r.json()
    result = body["result"]

    assert r.status_code == 201 and set(body) == RESPONSE_KEYS
    assert set(result) == RESULT_KEYS and result["pesticide_id"] == DRUG.id
    assert [c["key"] for c in result["checks"]] == ["registration", "timing", "count", "moa"]
    assert all(set(c) == CHECK_KEYS for c in result["checks"])
    assert all(set(c["evidence"]) == {"source_text", "data_asof"} for c in result["checks"])
    assert result["verdict"] in {"OK", "CAUTION", "BLOCKED", "NEEDS_CHECK"}
    assert result["data_asof"] == "2026-10-05"
    assert all(set(a) == ALT_KEYS for a in body["alternatives"])
    assert isinstance(body["show_extension_office"], bool)


def test_the_judgment_is_stored(client, db, farm):
    uid, zone = farm
    body = judge(
        client, uid, zone, pesticide_id=DRUG.id, pest_id=PEST, apply_date="2026-10-29"
    ).json()
    (row,) = stored(db, zone)

    assert row.id == body["judgment_id"]
    assert (row.pest_id, row.pesticide_id, row.apply_date.isoformat()) == (
        PEST,
        DRUG.id,
        "2026-10-29",
    )
    assert row.verdict == body["result"]["verdict"]
    assert row.result == body["result"]


def test_unspecified_pest_is_stored_as_null(client, db, farm):
    uid, zone = farm
    judge(client, uid, zone, pesticide_id=DRUG.id)

    assert [row.pest_id for row in stored(db, zone)] == [None]


def test_every_call_stores_its_own_row(client, db, farm):
    uid, zone = farm
    first = judge(client, uid, zone, pesticide_id=DRUG.id).json()
    second = judge(client, uid, zone, pesticide_id=DRUG.id).json()

    assert first["judgment_id"] != second["judgment_id"]
    assert [row.id for row in stored(db, zone)] == [first["judgment_id"], second["judgment_id"]]


def test_apply_date_defaults_to_today_kst_and_an_explicit_one_is_echoed(client, db, farm):
    uid, zone = farm
    default = judge(client, uid, zone, pesticide_id=DRUG.id).json()
    explicit = judge(client, uid, zone, pesticide_id=DRUG.id, apply_date="2026-01-15").json()

    assert default["apply_date"] == today_kst().isoformat()
    assert explicit["apply_date"] == "2026-01-15"
    assert [row.apply_date.isoformat() for row in stored(db, zone)] == [
        today_kst().isoformat(),
        "2026-01-15",
    ]


def test_stored_spray_is_counted_whatever_the_apply_date(client, db, farm):
    uid, zone = farm
    confirm(db, zone)
    pest_id, drug = counting_selection()

    def used(apply_date):
        body = judge(
            client, uid, zone, pesticide_id=drug.id, pest_id=pest_id, apply_date=apply_date
        ).json()
        return body["result"]["checks"][2]["facts"]["used"]

    assert used("2026-04-15") == 0
    sprayed = client.post(
        f"/zones/{zone}/sprays",
        json={
            "pesticide_id": drug.id,
            "source": "manual",
            "request_id": str(uuid.uuid4()),
            "sprayed_on": "2026-05-01",
        },
        headers=auth(uid),
    )
    assert sprayed.status_code == 201
    assert used("2026-04-15") == 1 and used("2026-10-29") == 1


def test_judgment_creates_no_spray_record(client, db, farm):
    uid, zone = farm
    judge(client, uid, zone, pesticide_id=DRUG.id, pest_id=PEST)

    assert db.scalar(text("SELECT count(*) FROM spray_log WHERE zone_id = :z"), {"z": zone}) == 0


def test_alternatives_and_the_office_flag(client, db, farm):
    uid, zone = farm
    chosen, pest = unregistered_drug(), pest_with_alternatives()
    request = {"pesticide_id": chosen.id, "pest_id": pest, "apply_date": TODAY.isoformat()}

    unconfirmed = judge(client, uid, zone, **request).json()  # nothing can be OK yet
    assert unconfirmed["result"]["verdict"] == "BLOCKED"
    assert (unconfirmed["alternatives"], unconfirmed["show_extension_office"]) == ([], True)

    confirm(db, zone)
    confirmed = judge(client, uid, zone, **request).json()
    keys = [(a["moa"]["label_kr"], a["item_name"], a["name"]) for a in confirmed["alternatives"]]
    ids = {a["id"] for a in confirmed["alternatives"]}

    assert confirmed["alternatives"] and confirmed["show_extension_office"] is False
    assert keys == sorted(keys)
    assert ids <= {d.id for d in pool(1, pest)} and chosen.id not in ids


def test_unspecified_pest_notice(client, farm):
    uid, zone = farm
    body = judge(client, uid, zone, pesticide_id=unregistered_drug().id).json()

    assert body["result"]["notices"] == [NOTICE]
    assert (body["alternatives"], body["show_extension_office"]) == ([], False)


def test_unregistered_drug_is_blocked_not_an_error(client, farm):
    uid, zone = farm
    r = judge(client, uid, zone, pesticide_id=unregistered_drug().id, pest_id=PEST)
    first_check = r.json()["result"]["checks"][0]

    assert r.status_code == 201 and r.json()["result"]["verdict"] == "BLOCKED"
    assert (first_check["status"], first_check["facts"]) == ("BLOCKED", {"crop_registered": False})
```
- [ ] **Step 2: Run** `.venv\Scripts\python -m pytest tests\test_judgment_api.py -q` — Expected: FAIL (the route does not exist: 404/405 instead of the expected results; collection must succeed).
- [ ] **Step 3: Implement** the repository, `Judgment` and `run_judgment`, the schemas, the router and the `include_router` line per the interface block.
- [ ] **Step 4: Run** the step 2 command — Expected: `20 passed` (1 auth, 1 foreign/unknown zone, 1 unknown pesticide, 2 pest 404, 1 apply date, 4 malformed, 1 shape, 1 stored, 1 null pest, 1 two rows, 1 apply date default, 1 stored spray, 1 no spray record, 1 alternatives, 1 notice, 1 unregistered). Whole suite and `ruff check .` clean.
- [ ] **Step 5: Commit** `git add app/judgment app/main.py tests/test_judgment_api.py` / `git commit -m "Add judgment endpoint"`

### Task 6: Mutation checks and final verification

- [ ] **Step 1: Mutation checks.** After each change run `tests\test_judgment_assess.py tests\test_judgment_api.py` and restore with `git checkout -- <file>`: (a) never append `NO_ALTERNATIVE_NOTICE` — Expected: both notice tests FAIL; (b) drop `not alternatives` from `show_extension_office` — Expected: the truth-table cases with `count=1` FAIL; (c) call `judge()` with `history=[]` — Expected: `test_history_is_converted_with_item_name_and_moa` and `test_stored_spray_is_counted_whatever_the_apply_date` FAIL; (d) remove the `apply_date` upper bound — Expected: `test_apply_date_after_2100_is_422_but_the_last_day_of_2100_is_accepted` FAILS (a 500); (e) leave the chosen drug in the alternatives pool — Expected: the alternatives invariants test FAILS. Re-run the whole suite — all pass; `git status --short` shows only the unrelated backlog xlsx and `.gitignore`.
- [ ] **Step 2:** In `docs/dev/팜가디언_아키텍처.md` §4 change the clause 「`judgment`에는 `infrastructure`가 없다」 to say that `judgment/infrastructure` holds only the repository that stores judgments (inputs still come through the other contexts' `application` services). One sentence, nothing else in that file or in `팜가디언_API_명세.md`. Commit `git add docs/dev/팜가디언_아키텍처.md` / `git commit -m "Note the judgment repository in the architecture"`.
- [ ] **Step 3:** `.venv\Scripts\python -m pytest -q -rs` and `.venv\Scripts\ruff check .` — Expected: all pass, `All checks passed!`.
- [ ] **Step 4:** `git diff --name-only origin/test..HEAD` lists no `팜가디언_API_명세.md`, no `schema.sql` and nothing under `app/judgment/domain`; `git log --oneline origin/test..HEAD` shows 7 commits (design and plan, catalog rows, history and reader, assessment, sweep, endpoint, architecture note). Do not push.
- [ ] **Step 5:** Tell the user: BE-45 done; Notion rows to update after the PR merges: 약제 판정 실행(4개 체크) → 완료; backlog xlsx: check BE-45. The `farm/application/zone_reader.py` is in 혜빈님's folder and needs her review. Next: BE-17~19 (auth), BE-23 (weather), BE-13 (OpenAPI export).
