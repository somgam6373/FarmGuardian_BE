# Spray Records Implementation Plan (BE-46, BE-47)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (project CLAUDE.md: no subagent-driven execution). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `POST /zones/{id}/sprays`, `GET /zones/{id}/sprays` and `DELETE /zones/{id}/sprays/{sid}` on the existing `spray_log` table, in the shape of the API spec §8.

**Architecture:** new bounded context `app/spraying/` (domain entity, SQL repository, application service that commits, FastAPI router and schemas). The service resolves each record's pesticide through a new `catalog_service.get_pesticide`. All routes sit behind `current_user` and `get_owned_zone`.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2 `text()` SQL on psycopg 3, Pydantic v2, pytest against the PostGIS test database (`db`, `client`, `make_user`, `make_field`, `make_zone` fixtures).

**Spec:** `docs/dev/2026-10-29-spray-records-design.md` (approved in chat 2026-10-29); frame = `docs/dev/팜가디언_API_명세.md` §8 (never edited).

## Global Constraints

- `팜가디언_API_명세.md` is the frame and **must not change**; `schema.sql` does not change either.
- A spray serializes to exactly `{id, pesticide: {id, name, item_name, moa}, sprayed_on, source}`; `moa` is `{label_kr, system, code}` or `null`; `source` is `"manual"` or `"app"`; `request_id` and `created_at` are never exposed. A list is `{total, items}`.
- Status codes: POST new 201, POST replay 200, DELETE 204 with an empty body, errors in the common `{"error": {code, message, details?}}` format.
- POST order: validate (unknown `pesticide_id` and `sprayed_on` after `today_kst()` are 422 with `loc` `["body", <field>]`, values never echoed) → same `request_id` in this zone returns 200 / in another zone is 422 `["body","request_id"]` with no record data → same zone, `pesticide_id` and `sprayed_on` without `allow_duplicate` is 409 `DUPLICATE_SPRAY` with `details.existing` = the lowest-id such record, after one more `request_id` re-check → insert with `ON CONFLICT (request_id) DO NOTHING`; a conflict is re-read and answered like the 200 case → commit → 201.
- Omitted `sprayed_on` = today (KST). GET: `limit` 1..100 (default 20), `offset` >= 0, order `sprayed_on` DESC then `id` DESC. DELETE removes only a record of the addressed zone; anything else is 404.
- Foreign or unknown zone is 404 and wins over body validation; missing/invalid `X-User-Id` is 401.
- The pesticide of a record may be any catalog drug, not only one registered for the zone's crop.
- Layers: `domain` imports nothing from the app; `presentation` calls only `application`; only the service imports `catalog_service`. No change to `app/core`.
- Code and identifiers in English, short Korean comments as in `app/core`; ruff line length 100 (Korean characters count double, wrap long strings); tests flat in `tests/`; commit messages in English; do not push.

## Review Focus

- A retry must never double-save: same `request_id` replay (200, one row), replay with a different body, the replay answered before the duplicate check, and both race paths (the insert conflict and the pre-409 re-check). (Task 2)
- A `request_id` already used in another zone or by another user is 422 and leaks nothing about that record. (Tasks 2, 3)
- A 409 stores nothing, so the same `request_id` can be resent with `allow_duplicate`. (Tasks 2, 3)
- Foreign zone with an invalid body answers 404, not 422. (Task 3)
- Cancel cannot touch another zone's record even with a valid id, and cancelling twice is 404. (Tasks 2, 3)

---

### Task 0: Commit the design and this plan

- [ ] **Step 1:** `git add docs/dev/2026-10-29-spray-records-design.md docs/dev/2026-10-29-spray-records-plan.md` / `git commit -m "Add spray records design and plan"` (do not stage `farmguardian_backlog_BE.xlsx`).

### Task 1: Catalog lookup and the shared pesticide schema

**Files:**
- Modify: `app/catalog/application/catalog_service.py`, `app/catalog/presentation/schemas.py`, `app/catalog/presentation/router.py`
- Test: `tests/test_catalog_pesticide_shape.py`

**Interfaces:**
- Produces in `catalog_service.py`: `get_pesticide(pesticide_id: int) -> Pesticide | None` (an id index over the cached `_drugs()`).
- Produces in `schemas.py`: `PesticideBase(id: int, name: str, item_name: str, moa: MoaOut | None)`; `PesticideOut(PesticideBase)` adds `at_planting_only: bool`; `pesticide_base(p: Pesticide) -> PesticideBase`. `router._pesticide_out` is rebuilt on `pesticide_base`; `GET /pesticides` output does not change.

- [ ] **Step 1: Write the failing tests** in `tests/test_catalog_pesticide_shape.py`
```python
from app.catalog.application import catalog_service as svc
from app.catalog.domain.entities import Moa, Pesticide
from app.catalog.presentation.schemas import PesticideBase, PesticideOut, pesticide_base


def all_drugs():
    return [e.pesticide for crop_id in (1, 2, 3) for e in svc.list_pesticides(crop_id)]


def test_every_drug_is_found_by_its_id():
    for drug in all_drugs():
        assert svc.get_pesticide(drug.id) == drug


def test_distinct_drug_count():
    assert len({d.id for d in all_drugs()}) == 1363


def test_unknown_ids_are_none():
    for pesticide_id in (0, -1, 999999):
        assert svc.get_pesticide(pesticide_id) is None


def test_pesticide_base_has_the_four_spec_fields():
    assert set(PesticideBase.model_fields) == {"id", "name", "item_name", "moa"}
    assert set(PesticideOut.model_fields) == {"id", "name", "item_name", "moa", "at_planting_only"}


def test_pesticide_base_converter():
    drug = Pesticide(7, "Brand", "Item", Moa("라3", "FRAC", "24"))

    assert pesticide_base(drug).model_dump() == {
        "id": 7,
        "name": "Brand",
        "item_name": "Item",
        "moa": {"label_kr": "라3", "system": "FRAC", "code": "24"},
    }
    assert pesticide_base(Pesticide(8, "B", "I", None)).moa is None
```
- [ ] **Step 2: Run** `.venv\Scripts\python -m pytest tests\test_catalog_pesticide_shape.py -q` — Expected: collection ERROR (`cannot import name 'pesticide_base'`).
- [ ] **Step 3: Implement** the three interface items per the block above. `PesticideOut` keeps its field order (`id, name, item_name, moa, at_planting_only`).
- [ ] **Step 4: Run** the step 2 command — Expected: `5 passed`. Then the whole suite (`GET /pesticides` tests in `tests/test_catalog_api.py` must stay green: `717 passed`) and `ruff check .` clean.
- [ ] **Step 5: Commit** `git add app/catalog tests/test_catalog_pesticide_shape.py` / `git commit -m "Add pesticide lookup by id"`

### Task 2: Spraying domain, repository and service

**Files:**
- Create: `app/spraying/__init__.py`, `app/spraying/domain/__init__.py`, `app/spraying/domain/entities.py`, `app/spraying/infrastructure/__init__.py`, `app/spraying/infrastructure/repository.py`, `app/spraying/application/__init__.py`, `app/spraying/application/spray_service.py`
- Test: `tests/test_spray_service.py`

**Interfaces:**
- Consumes: `catalog_service.get_pesticide` (Task 1), `AppError`.
- Produces in `entities.py`: `Spray(id: int, pesticide_id: int, sprayed_on: date, source: str)` (frozen dataclass).
- Produces in `repository.py` (plain functions on a `Session`, module-level so tests can patch them): `find_by_request_id(db, request_id: UUID) -> tuple[Spray, int] | None` (the record and its zone id); `find_duplicate(db, zone_id: int, pesticide_id: int, sprayed_on: date) -> Spray | None` (lowest id); `insert(db, zone_id, pesticide_id, sprayed_on, source, request_id) -> Spray | None` (`ON CONFLICT (request_id) DO NOTHING RETURNING`, None on conflict); `page(db, zone_id: int, limit: int, offset: int) -> tuple[int, list[Spray]]`; `delete(db, zone_id: int, spray_id: int) -> bool`. No commits here.
- Produces in `spray_service.py`: `SprayView(spray: Spray, pesticide: Pesticide)`; `class DuplicateSpray(Exception)` with attribute `existing: SprayView`; `record_spray(db, zone_id: int, *, pesticide_id: int, sprayed_on: date | None, source: str, request_id: UUID, allow_duplicate: bool, today: date) -> tuple[SprayView, bool]` (the bool is `created`); `list_sprays(db, zone_id: int, limit: int = 20, offset: int = 0) -> tuple[int, list[SprayView]]`; `cancel_spray(db, zone_id: int, spray_id: int) -> None` (404 `AppError` when nothing was deleted). The service commits after insert and delete. It calls the repository through the module (`repository.find_by_request_id(...)`) so tests can patch it.
- Errors raised as `AppError("VALIDATION_ERROR", 422, <message>, {"errors": [{"loc": ["body", <field>], "msg": <message>, "type": "value_error"}]})` through one private helper; the message never contains the submitted value.

- [ ] **Step 1: Write the failing tests** in `tests/test_spray_service.py`
```python
import uuid
from datetime import date, timedelta

import pytest

from app.catalog.application import catalog_service as catalog
from app.core.errors import AppError
from app.spraying.application import spray_service as svc
from app.spraying.application.spray_service import DuplicateSpray
from app.spraying.infrastructure import repository

TODAY = date(2026, 10, 29)
A, B = [e.pesticide.id for e in catalog.list_pesticides(1)[:2]]


@pytest.fixture
def zones(make_user, make_field, make_zone):
    uid = make_user("farmer")
    field = make_field(uid)
    return make_zone(field, uid), make_zone(field, uid)


def record(db, zone, pesticide_id=A, **kw):
    args = {
        "pesticide_id": pesticide_id,
        "sprayed_on": TODAY,
        "source": "manual",
        "request_id": uuid.uuid4(),
        "allow_duplicate": False,
        "today": TODAY,
    }
    return svc.record_spray(db, zone, **{**args, **kw})


def total(db, zone):
    return svc.list_sprays(db, zone)[0]


def test_record_returns_the_saved_spray_and_created_flag(db, zones):
    view, created = record(db, zones[0], source="app")

    assert created is True
    assert (view.spray.pesticide_id, view.spray.sprayed_on, view.spray.source) == (A, TODAY, "app")
    assert view.pesticide.id == A
    assert view.spray.id > 0


def test_omitted_date_defaults_to_today(db, zones):
    view, _ = record(db, zones[0], sprayed_on=None)

    assert view.spray.sprayed_on == TODAY


def test_today_and_past_are_valid_but_tomorrow_is_422(db, zones):
    record(db, zones[0], sprayed_on=TODAY)
    record(db, zones[0], sprayed_on=date(2020, 1, 1))
    with pytest.raises(AppError) as info:
        record(db, zones[0], sprayed_on=TODAY + timedelta(days=1))

    assert (info.value.status, info.value.code) == (422, "VALIDATION_ERROR")
    assert info.value.details["errors"][0]["loc"] == ["body", "sprayed_on"]
    assert "2026-10-30" not in str(info.value.details)
    assert total(db, zones[0]) == 2


def test_unknown_pesticide_is_422_and_stores_nothing(db, zones):
    with pytest.raises(AppError) as info:
        record(db, zones[0], 999999)

    assert (info.value.status, info.value.code) == (422, "VALIDATION_ERROR")
    assert info.value.details["errors"][0]["loc"] == ["body", "pesticide_id"]
    assert "999999" not in str(info.value.details)
    assert total(db, zones[0]) == 0


def test_same_request_id_returns_the_stored_spray_without_saving_again(db, zones):
    rid = uuid.uuid4()
    first, created_first = record(db, zones[0], request_id=rid)
    again, created_again = record(db, zones[0], request_id=rid)

    assert (created_first, created_again) == (True, False)
    assert again.spray.id == first.spray.id
    assert total(db, zones[0]) == 1


def test_replay_returns_the_original_even_if_the_retry_differs(db, zones):
    rid = uuid.uuid4()
    first, _ = record(db, zones[0], A, request_id=rid)
    again, created = record(
        db, zones[0], B, request_id=rid, sprayed_on=TODAY - timedelta(days=3)
    )

    assert created is False and again.spray.id == first.spray.id
    assert (again.spray.pesticide_id, again.spray.sprayed_on) == (A, TODAY)


def test_request_id_of_another_zone_is_422_and_leaks_nothing(db, zones):
    rid = uuid.uuid4()
    record(db, zones[0], request_id=rid)
    with pytest.raises(AppError) as info:
        record(db, zones[1], B, request_id=rid)

    assert (info.value.status, info.value.code) == (422, "VALIDATION_ERROR")
    assert info.value.details["errors"][0]["loc"] == ["body", "request_id"]
    assert total(db, zones[1]) == 0


def test_duplicate_raises_with_the_existing_spray_and_stores_nothing(db, zones):
    first, _ = record(db, zones[0])
    with pytest.raises(DuplicateSpray) as info:
        record(db, zones[0])

    assert info.value.existing.spray.id == first.spray.id
    assert info.value.existing.pesticide.id == A
    assert total(db, zones[0]) == 1


def test_allow_duplicate_saves_a_second_record(db, zones):
    first, _ = record(db, zones[0])
    second, created = record(db, zones[0], allow_duplicate=True)

    assert created is True and second.spray.id != first.spray.id
    assert total(db, zones[0]) == 2


def test_resending_a_409_request_id_with_allow_duplicate_saves(db, zones):
    record(db, zones[0])
    rid = uuid.uuid4()
    with pytest.raises(DuplicateSpray):
        record(db, zones[0], request_id=rid)
    _, created = record(db, zones[0], request_id=rid, allow_duplicate=True)

    assert created is True
    assert total(db, zones[0]) == 2


def test_existing_is_the_oldest_duplicate(db, zones):
    first, _ = record(db, zones[0])
    record(db, zones[0], allow_duplicate=True)
    with pytest.raises(DuplicateSpray) as info:
        record(db, zones[0])

    assert info.value.existing.spray.id == first.spray.id


@pytest.mark.parametrize(
    "change", [{"sprayed_on": TODAY - timedelta(days=1)}, {"pesticide_id": B}], ids=["date", "drug"]
)
def test_other_date_or_pesticide_is_not_a_duplicate(db, zones, change):
    record(db, zones[0])
    _, created = record(db, zones[0], **change)

    assert created is True


def test_same_spray_in_another_zone_is_not_a_duplicate(db, zones):
    record(db, zones[0])
    _, created = record(db, zones[1])

    assert created is True


def stale_first_lookup(monkeypatch):
    # 경쟁 요청이 막 저장한 뒤인데도 첫 조회는 빈손으로 돌아오는 상황
    real, calls = repository.find_by_request_id, []

    def stale(db, request_id):
        calls.append(request_id)
        return None if len(calls) == 1 else real(db, request_id)

    monkeypatch.setattr(repository, "find_by_request_id", stale)


@pytest.mark.parametrize("allow_duplicate", [False, True])
def test_lost_race_is_answered_as_a_replay(db, zones, monkeypatch, allow_duplicate):
    rid = uuid.uuid4()
    first, _ = record(db, zones[0], request_id=rid)
    stale_first_lookup(monkeypatch)
    again, created = record(db, zones[0], request_id=rid, allow_duplicate=allow_duplicate)

    assert created is False and again.spray.id == first.spray.id
    assert total(db, zones[0]) == 1


def test_insert_with_a_used_request_id_returns_none(db, zones):
    rid = uuid.uuid4()

    assert repository.insert(db, zones[0], A, TODAY, "manual", rid) is not None
    assert repository.insert(db, zones[0], B, TODAY, "app", rid) is None
    assert repository.page(db, zones[0], 20, 0)[0] == 1


def test_list_orders_by_date_then_id_descending(db, zones):
    old, _ = record(db, zones[0], A, sprayed_on=TODAY - timedelta(days=5))
    new_a, _ = record(db, zones[0], A, sprayed_on=TODAY)
    new_b, _ = record(db, zones[0], B, sprayed_on=TODAY)
    count, items = svc.list_sprays(db, zones[0])

    assert count == 3
    assert [v.spray.id for v in items] == [new_b.spray.id, new_a.spray.id, old.spray.id]


def test_list_pages_and_total_counts_everything(db, zones):
    ids = [
        record(db, zones[0], A, sprayed_on=TODAY - timedelta(days=i))[0].spray.id
        for i in range(5)
    ]
    count, page = svc.list_sprays(db, zones[0], limit=2, offset=1)

    assert count == 5
    assert [v.spray.id for v in page] == ids[1:3]
    assert svc.list_sprays(db, zones[0], limit=2, offset=10) == (5, [])


def test_list_excludes_other_zones_and_resolves_the_pesticide(db, zones):
    record(db, zones[0], A)
    record(db, zones[1], B)
    count, items = svc.list_sprays(db, zones[0])

    assert count == 1
    assert items[0].pesticide == catalog.get_pesticide(A)


def test_cancel_removes_the_record(db, zones):
    view, _ = record(db, zones[0])
    svc.cancel_spray(db, zones[0], view.spray.id)

    assert total(db, zones[0]) == 0


def test_cancel_twice_or_unknown_is_404(db, zones):
    view, _ = record(db, zones[0])
    svc.cancel_spray(db, zones[0], view.spray.id)
    for spray_id in (view.spray.id, 999999):
        with pytest.raises(AppError) as info:
            svc.cancel_spray(db, zones[0], spray_id)

        assert (info.value.status, info.value.code) == (404, "NOT_FOUND")


def test_cancel_of_another_zones_record_is_404_and_keeps_it(db, zones):
    view, _ = record(db, zones[1])
    with pytest.raises(AppError) as info:
        svc.cancel_spray(db, zones[0], view.spray.id)

    assert info.value.status == 404
    assert total(db, zones[1]) == 1
```
- [ ] **Step 2: Run** `.venv\Scripts\python -m pytest tests\test_spray_service.py -q` — Expected: collection ERROR (`No module named 'app.spraying'`).
- [ ] **Step 3: Implement** the entity, the five repository functions and the service per the interface block and Global Constraints (`text()` SQL like `app/core/auth.py`; the service resolves each record's pesticide with `catalog_service.get_pesticide`; commit after insert and after a successful delete; the pre-409 re-check is a second call of the same replay helper).
- [ ] **Step 4: Run** the step 2 command — Expected: `23 passed`. Whole suite `740 passed` and `ruff check .` clean (wrap long lines).
- [ ] **Step 5: Commit** `git add app/spraying tests/test_spray_service.py` / `git commit -m "Add spray record service"`

### Task 3: Endpoints

**Files:**
- Create: `app/spraying/presentation/__init__.py`, `app/spraying/presentation/schemas.py`, `app/spraying/presentation/router.py`
- Modify: `app/main.py`
- Test: `tests/test_spray_api.py`

**Interfaces:**
- Consumes: Task 2 service, `pesticide_base`/`PesticideBase` (Task 1), `current_user`, `get_owned_zone`, `get_db`, `today_kst`.
- Produces: `SprayIn(pesticide_id: int, sprayed_on: date | None = None, source: Literal["manual","app"], request_id: UUID, allow_duplicate: bool = False)`; `SprayOut(id: int, pesticide: PesticideBase, sprayed_on: date, source: Literal["manual","app"])`; `SprayPage(total: int, items: list[SprayOut])`; `router = APIRouter(dependencies=[Depends(current_user)])` with `POST /zones/{zone_id}/sprays` (201; `Response` parameter sets 200 on a replay; a `DuplicateSpray` becomes `AppError("DUPLICATE_SPRAY", 409, <message>, {"existing": <SprayOut as JSON>})`), `GET /zones/{zone_id}/sprays` (`limit: Query(20, ge=1, le=100)`, `offset: Query(0, ge=0)`) and `DELETE /zones/{zone_id}/sprays/{spray_id}` (204, empty body). The zone comes from `Depends(get_owned_zone)`.

- [ ] **Step 1: Write the failing tests** in `tests/test_spray_api.py`
```python
import uuid
from datetime import timedelta

import pytest

from app.catalog.application import catalog_service as catalog
from app.core.time import today_kst

SPRAY_KEYS = {"id", "pesticide", "sprayed_on", "source"}
PESTICIDE_KEYS = {"id", "name", "item_name", "moa"}
DRUGS = [e.pesticide for e in catalog.list_pesticides(1)]
WITH_MOA = next(d for d in DRUGS if d.moa)
WITHOUT_MOA = next(d for d in DRUGS if d.moa is None)


def auth(uid):
    return {"X-User-Id": str(uid)}


@pytest.fixture
def farm(make_user, make_field, make_zone):
    uid = make_user("farmer")
    return uid, make_zone(make_field(uid), uid)


def save(client, uid, zone, pesticide_id=WITH_MOA.id, **kw):
    body = {"pesticide_id": pesticide_id, "source": "manual", "request_id": str(uuid.uuid4())}
    return client.post(f"/zones/{zone}/sprays", json={**body, **kw}, headers=auth(uid))


def listing(client, uid, zone, **params):
    return client.get(f"/zones/{zone}/sprays", params=params, headers=auth(uid))


@pytest.mark.parametrize(
    "method,path",
    [("post", "/zones/1/sprays"), ("get", "/zones/1/sprays"), ("delete", "/zones/1/sprays/1")],
)
def test_requires_authentication(client, method, path):
    r = client.request(method, path, json={} if method == "post" else None)

    assert (r.status_code, r.json()["error"]["code"]) == (401, "UNAUTHORIZED")


def test_foreign_and_unknown_zones_are_404(client, make_user, make_field, make_zone, farm):
    uid, _ = farm
    other = make_user("other")
    foreign = make_zone(make_field(other), other)
    for zone in (foreign, 999999):
        responses = [
            client.post(f"/zones/{zone}/sprays", json={}, headers=auth(uid)),  # 404 beats 422
            listing(client, uid, zone),
            client.delete(f"/zones/{zone}/sprays/1", headers=auth(uid)),
        ]

        assert [(r.status_code, r.json()["error"]["code"]) for r in responses] == [
            (404, "NOT_FOUND")
        ] * 3


def test_post_creates_and_returns_the_spray(client, farm):
    uid, zone = farm
    r = save(client, uid, zone, sprayed_on="2026-01-05", source="app")
    body = r.json()

    assert r.status_code == 201
    assert set(body) == SPRAY_KEYS and set(body["pesticide"]) == PESTICIDE_KEYS
    assert (body["sprayed_on"], body["source"]) == ("2026-01-05", "app")
    assert body["pesticide"]["id"] == WITH_MOA.id
    assert body["pesticide"]["name"] == WITH_MOA.name
    assert body["pesticide"]["item_name"] == WITH_MOA.item_name
    assert body["pesticide"]["moa"] == {
        "label_kr": WITH_MOA.moa.label_kr,
        "system": WITH_MOA.moa.system,
        "code": WITH_MOA.moa.code,
    }


def test_pesticide_without_moa_has_null_moa(client, farm):
    uid, zone = farm

    assert save(client, uid, zone, WITHOUT_MOA.id).json()["pesticide"]["moa"] is None


def test_omitted_date_is_today_kst(client, farm):
    uid, zone = farm

    assert save(client, uid, zone).json()["sprayed_on"] == today_kst().isoformat()


def test_future_date_is_422_and_today_is_accepted(client, farm):
    uid, zone = farm
    tomorrow = (today_kst() + timedelta(days=1)).isoformat()
    r = save(client, uid, zone, sprayed_on=tomorrow)
    error = r.json()["error"]

    assert (r.status_code, error["code"]) == (422, "VALIDATION_ERROR")
    assert error["details"]["errors"][0]["loc"] == ["body", "sprayed_on"]
    assert tomorrow not in str(error)
    assert save(client, uid, zone, sprayed_on=today_kst().isoformat()).status_code == 201
    assert listing(client, uid, zone).json()["total"] == 1


@pytest.mark.parametrize(
    "patch,field",
    [
        ({"pesticide_id": 999999}, "pesticide_id"),
        ({"pesticide_id": "abc"}, "pesticide_id"),
        ({"source": "robot"}, "source"),
        ({"request_id": "not-a-uuid"}, "request_id"),
        ({"sprayed_on": "2026-13-45"}, "sprayed_on"),
    ],
)
def test_invalid_values_are_422_with_their_location(client, farm, patch, field):
    uid, zone = farm
    r = save(client, uid, zone, **patch)
    error = r.json()["error"]

    assert (r.status_code, error["code"]) == (422, "VALIDATION_ERROR")
    assert error["details"]["errors"][0]["loc"] == ["body", field]


@pytest.mark.parametrize("field", ["pesticide_id", "source", "request_id"])
def test_missing_required_field_is_422(client, farm, field):
    uid, zone = farm
    body = {"pesticide_id": WITH_MOA.id, "source": "manual", "request_id": str(uuid.uuid4())}
    del body[field]
    r = client.post(f"/zones/{zone}/sprays", json=body, headers=auth(uid))

    assert r.status_code == 422
    assert r.json()["error"]["details"]["errors"][0]["loc"] == ["body", field]


def test_retry_with_the_same_request_id_returns_200_and_stores_once(client, farm):
    uid, zone = farm
    rid = str(uuid.uuid4())
    first = save(client, uid, zone, request_id=rid)
    again = save(client, uid, zone, request_id=rid)

    assert (first.status_code, again.status_code) == (201, 200)
    assert again.json() == first.json()
    assert listing(client, uid, zone).json()["total"] == 1


def test_request_id_of_another_zone_or_user_is_422_without_a_record(
    client, make_user, make_field, make_zone, farm
):
    uid, zone = farm
    rid = str(uuid.uuid4())
    save(client, uid, zone, request_id=rid)
    other = make_user("other")
    targets = [(uid, make_zone(make_field(uid), uid)), (other, make_zone(make_field(other), other))]
    for user, target in targets:
        r = save(client, user, target, request_id=rid)
        error = r.json()["error"]

        assert (r.status_code, error["code"]) == (422, "VALIDATION_ERROR")
        assert error["details"]["errors"][0]["loc"] == ["body", "request_id"]
        assert listing(client, user, target).json() == {"total": 0, "items": []}


def test_duplicate_is_409_with_the_existing_spray(client, farm):
    uid, zone = farm
    first = save(client, uid, zone, sprayed_on="2026-01-05")
    r = save(client, uid, zone, sprayed_on="2026-01-05")
    error = r.json()["error"]

    assert (r.status_code, error["code"]) == (409, "DUPLICATE_SPRAY")
    assert error["details"] == {"existing": first.json()}
    assert listing(client, uid, zone).json()["total"] == 1


def test_resending_the_409_request_id_with_allow_duplicate_saves(client, farm):
    uid, zone = farm
    rid = str(uuid.uuid4())
    save(client, uid, zone, sprayed_on="2026-01-05")

    assert save(client, uid, zone, sprayed_on="2026-01-05", request_id=rid).status_code == 409
    r = save(client, uid, zone, sprayed_on="2026-01-05", request_id=rid, allow_duplicate=True)

    assert r.status_code == 201
    assert listing(client, uid, zone).json()["total"] == 2


def test_list_shape_order_and_paging(client, farm):
    uid, zone = farm
    ids = [save(client, uid, zone, sprayed_on=f"2026-01-0{d}").json()["id"] for d in (1, 2, 3, 4)]
    page = listing(client, uid, zone, limit=2, offset=1).json()

    assert set(page) == {"total", "items"} and page["total"] == 4
    assert [s["id"] for s in page["items"]] == [ids[2], ids[1]]
    assert all(set(s) == SPRAY_KEYS for s in page["items"])
    assert [s["id"] for s in listing(client, uid, zone).json()["items"]] == ids[::-1]


def test_empty_history(client, farm):
    uid, zone = farm

    assert listing(client, uid, zone).json() == {"total": 0, "items": []}


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"limit": "x"}])
def test_list_bounds_are_422(client, farm, params):
    uid, zone = farm
    r = listing(client, uid, zone, **params)

    assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_ERROR")


def test_limit_100_is_accepted(client, farm):
    uid, zone = farm

    assert listing(client, uid, zone, limit=100).status_code == 200


def test_cancel_returns_204_and_removes_the_spray(client, farm):
    uid, zone = farm
    spray = save(client, uid, zone).json()
    r = client.delete(f"/zones/{zone}/sprays/{spray['id']}", headers=auth(uid))

    assert (r.status_code, r.content) == (204, b"")
    assert listing(client, uid, zone).json()["total"] == 0
    again = client.delete(f"/zones/{zone}/sprays/{spray['id']}", headers=auth(uid))
    assert (again.status_code, again.json()["error"]["code"]) == (404, "NOT_FOUND")


def test_cancel_of_another_zones_spray_is_404(client, make_field, make_zone, farm):
    uid, zone = farm
    zone2 = make_zone(make_field(uid), uid)
    spray = save(client, uid, zone2).json()
    r = client.delete(f"/zones/{zone}/sprays/{spray['id']}", headers=auth(uid))

    assert (r.status_code, r.json()["error"]["code"]) == (404, "NOT_FOUND")
    assert listing(client, uid, zone2).json()["total"] == 1


def test_non_integer_spray_id_is_422(client, farm):
    uid, zone = farm
    r = client.delete(f"/zones/{zone}/sprays/abc", headers=auth(uid))

    assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_ERROR")
```
- [ ] **Step 2: Run** `.venv\Scripts\python -m pytest tests\test_spray_api.py -q` — Expected: FAIL (the routes do not exist: 404/405 instead of the expected results; collection must succeed).
- [ ] **Step 3: Implement** the schemas, the router and the `include_router` line in `app/main.py` per the interface block.
- [ ] **Step 4: Run** the step 2 command — Expected: `30 passed` (3 auth, 1 foreign, 1 post, 1 no-moa, 1 default date, 1 future, 5 invalid, 3 missing, 1 retry, 1 other zone/user, 1 duplicate, 1 resend, 1 list, 1 empty, 4 bounds, 1 limit 100, 1 cancel, 1 cancel other zone, 1 non-integer). Whole suite `770 passed` and `ruff check .` clean.
- [ ] **Step 5: Commit** `git add app/spraying/presentation app/main.py tests/test_spray_api.py` / `git commit -m "Add spray endpoints"`
- [ ] **Step 6: Mutation checks.** Run `tests\test_spray_service.py tests\test_spray_api.py` after each change and restore with `git checkout -- <file>`: (a) in `record_spray` run the duplicate check before the `request_id` replay — Expected: `test_same_request_id_returns_the_stored_spray_without_saving_again` and the API retry test FAIL; (b) drop the `zone_id` condition from `repository.delete` — Expected: both cancel-of-another-zone tests FAIL; (c) order `page` by `sprayed_on` ascending — Expected: the order and paging tests FAIL; (d) remove the re-check before raising `DuplicateSpray` — Expected: `test_lost_race_is_answered_as_a_replay[False]` FAILS. Re-run the whole suite — all pass; `git status --short` shows only the backlog xlsx.

### Task 4: Final verification

- [ ] **Step 1:** `.venv\Scripts\python -m pytest -q -rs` and `.venv\Scripts\ruff check .` — Expected: `770 passed`, `All checks passed!`.
- [ ] **Step 2:** `git diff --name-only origin/test..HEAD` lists no `팜가디언_API_명세.md` and no `schema.sql`; `git log --oneline origin/test..HEAD` shows 4 commits; do not push.
- [ ] **Step 3:** Tell the user: BE-46·47 done; next BE-45 (judgment API; needs 혜빈님's zone interface agreed first). Notion rows to update after the PR merges: 살포 기록 저장, 살포 이력 조회, 살포 기록 취소; backlog xlsx: check BE-46, BE-47.
