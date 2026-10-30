import uuid

from sqlalchemy import text

from app.catalog.application import catalog_service
from app.farm.infrastructure.integrations import farmmap
from app.farm.infrastructure.integrations.farmmap import FarmmapParcel
from tests.judgment_scenarios import pest_with_alternatives, pool, unregistered_drug

CHECK_ORDER = ["registration", "timing", "count", "moa"]


def _square(farmmap_id: str) -> FarmmapParcel:
    """id 1·2는 나란히 놓인 10 x 10 필지 (합치면 20 x 10 밭)."""
    x0 = 10.0 * (int(farmmap_id) - 1)
    ring = [(x0, 0.0), (x0 + 10, 0.0), (x0 + 10, 10.0), (x0, 10.0), (x0, 0.0)]
    return FarmmapParcel(farmmap_id, "1" * 19, "1전", "밭", 2022, [[ring]])


def expect(response, status, step):
    assert response.status_code == status, f"{step}: {response.status_code} {response.text}"
    return response.json() if response.content else None


def test_the_user_scenario_end_to_end(client, db, monkeypatch):
    monkeypatch.setattr(
        farmmap, "parcel_by_id", lambda farmmap_id, *, client=None: _square(farmmap_id)
    )
    pest = pest_with_alternatives(2)
    chosen = unregistered_drug(2)  # 이 작물에 등록되지 않은 약제 → ① 불가, 대안이 나온다
    in_pool = {drug.id for drug in pool(2, pest)}
    history_drugs = [e.pesticide for e in catalog_service.list_pesticides(2)
                     if e.pesticide.id not in in_pool][:2]
    assert len(history_drugs) == 2

    # 1. 가입과 첫 밭
    signup = expect(client.post("/auth/signup", json={
        "username": "e2e_kim", "password": "pw1234", "field_name": "뒷밭",
        "parcel_farmmap_ids": ["1", "2"]}), 201, "signup")
    uid, field = signup["id"], signup["field"]
    auth = {"X-User-Id": str(uid)}
    assert field["zones"] == [] and abs(field["area_m2"] - 200) < 1, "signup: field"
    assert expect(client.get("/me", headers=auth), 200, "me")["onboarded"] is False
    assert len(expect(client.get("/crops", headers=auth), 200, "crops")) == 3

    # 2. 분할 미리보기와 구역 생성 (혜빈님 API는 호출만 한다)
    split = {"direction": "crosswise", "ratios": [6, 4]}
    pieces = expect(client.post(f"/fields/{field['id']}/split-preview", json=split,
                                headers=auth), 200, "split-preview")
    assert len(pieces) == 2 and abs(sum(p["area_m2"] for p in pieces) - 200) < 1, "split-preview"
    zones = expect(client.post(f"/fields/{field['id']}/zones", headers=auth, json={
        **split, "zones": [{"name": "A구역", "crop_id": 2, "planted_at": "2026-09-10"},
                           {"name": "B구역", "crop_id": 1}]}), 201, "zones")
    by_name = {z["name"]: z for z in zones}
    zone_a, zone_b = by_name["A구역"]["id"], by_name["B구역"]["id"]
    assert {"id", "field_id", "name", "crop", "planted_at", "history_confirmed", "area_m2",
            "geometry", "bbox"} <= set(zones[0]), "zones: Zone keys"

    # 3. 과거 살포 입력, 이력 확인, 취소와 다시 입력
    def spray(zone, drug_id, day, request_id=None, status=201, step="spray"):
        body = {"pesticide_id": drug_id, "sprayed_on": day, "source": "manual",
                "request_id": request_id or str(uuid.uuid4())}
        return expect(client.post(f"/zones/{zone}/sprays", json=body, headers=auth), status, step)

    def history(zone):
        return expect(client.get(f"/zones/{zone}/sprays", headers=auth), 200, "history")

    first = spray(zone_a, history_drugs[0].id, "2026-10-01", step="past spray 1")
    spray(zone_a, history_drugs[1].id, "2026-10-05", step="past spray 2")
    assert history(zone_a)["total"] == 2
    expect(client.delete(f"/zones/{zone_a}/sprays/{first['id']}", headers=auth), 204, "cancel")
    assert history(zone_a)["total"] == 1
    spray(zone_a, history_drugs[0].id, "2026-10-01", step="past spray again")
    assert history(zone_a)["total"] == 2

    # 4. 온보딩: 확인 전에는 422, 모든 구역을 확인하면 200
    incomplete = expect(client.post("/me/onboarding", headers=auth), 422, "onboarding before")
    assert incomplete["error"]["code"] == "ONBOARDING_INCOMPLETE"
    assert incomplete["error"]["details"]["unconfirmed_zone_ids"] == sorted([zone_a, zone_b])
    # PATCH /zones/{id}가 생기면 이 줄을 API 호출로 바꾼다
    db.execute(text("UPDATE zone SET history_confirmed = true WHERE user_id = :u"), {"u": uid})
    expect(client.post("/me/onboarding", headers=auth), 200, "onboarding after")
    assert expect(client.get("/me", headers=auth), 200, "me")["onboarded"] is True
    summaries = {z["name"]: z for z in expect(client.get("/fields", headers=auth), 200,
                                              "fields")[0]["zones"]}
    assert summaries["A구역"]["last_spray"] is not None and summaries["B구역"]["last_spray"] is None

    # 5. 병해충과 약제 고르기
    parts = expect(client.get("/crops/2/symptom-parts", headers=auth), 200, "symptom-parts")
    assert parts, "symptom-parts: empty"
    candidates = expect(client.get("/pests/candidates", params={"crop_id": 2, "part": parts[0]},
                                   headers=auth), 200, "candidates")
    assert candidates, "candidates: empty"
    listed = expect(client.get("/pests", params={"crop_id": 2}, headers=auth), 200, "pests")
    assert pest in {p["id"] for p in listed}, "pests: the chosen pest is missing"
    drugs = expect(client.get("/pesticides", params={"crop_id": 2, "pest_id": pest},
                              headers=auth), 200, "pesticides")
    assert drugs, "pesticides: empty"

    # 6. 판정 (저장은 하지 않는다)
    before = history(zone_a)["total"]
    judged = expect(client.post(f"/zones/{zone_a}/judgments", headers=auth,
                                json={"pesticide_id": chosen.id, "pest_id": pest}), 201, "judgment")
    result = judged["result"]
    assert [c["key"] for c in result["checks"]] == CHECK_ORDER, "judgment: check order"
    assert result["verdict"] == "BLOCKED", "judgment: unregistered drug"
    alternatives = judged["alternatives"]
    assert alternatives and judged["show_extension_office"] is False, "judgment: alternatives"
    label = (result["moa"] or {}).get("label_kr")
    assert all(a["moa"] and a["moa"]["label_kr"] != label for a in alternatives), "alt: moa"
    assert history(zone_a)["total"] == before, "judgment must not save a spray"

    # 7. 대안으로 살포 저장: 재시도는 같은 기록, 같은 날 같은 약은 409
    request_id = str(uuid.uuid4())
    saved = spray(zone_a, alternatives[0]["id"], "2026-10-20", request_id, step="save alternative")
    duplicate = spray(zone_a, alternatives[0]["id"], "2026-10-20", status=409, step="duplicate")
    assert duplicate["error"]["code"] == "DUPLICATE_SPRAY"
    assert duplicate["error"]["details"]["existing"]["id"] == saved["id"]
    replay = spray(zone_a, alternatives[0]["id"], "2026-10-20", request_id, 200, step="replay")
    assert replay["id"] == saved["id"]

    # 8. 밭 삭제는 구역과 기록까지 지운다
    expect(client.delete(f"/fields/{field['id']}", headers=auth), 204, "delete field")
    assert expect(client.get("/fields", headers=auth), 200, "fields") == []
    expect(client.get(f"/zones/{zone_a}/sprays", headers=auth), 404, "sprays of a deleted zone")

    # 9. 탈퇴
    expect(client.delete("/me", headers=auth), 204, "withdraw")
    expect(client.get("/me", headers=auth), 401, "me after withdrawal")
    assert db.scalar(text("SELECT count(*) FROM users WHERE id = :u"), {"u": uid}) == 0
