import functools

from app.catalog.domain.entities import Crop, Moa, Pesticide, PesticideEntry
from app.catalog.infrastructure.static_data import load
from app.core.errors import AppError


def _moa(moa_code: str | None, intl_codes: dict[str, str | None]) -> Moa | None:
    if not moa_code:
        return None
    if "+" in moa_code:  # 복합 계열은 성분의 국제 코드를 따로 두지 않는다
        return Moa(moa_code, None, None)
    system, _, code = (intl_codes.get(moa_code) or "").partition(" ")
    return Moa(moa_code, system or None, code or None)


@functools.cache
def _crops() -> dict[int, str]:
    return {c["crop_id"]: c["name"] for c in load("crop")}


@functools.cache
def _pest_crops() -> dict[int, int]:
    return {p["pest_id"]: p["crop_id"] for p in load("pest")}


@functools.cache
def _drugs() -> tuple[tuple[Pesticide, tuple[tuple[int, int, str], ...]], ...]:
    """약제 = (품목명, 상표명). 모든 작물에서 가장 작은 use_id가 약제 id다.
    각 약제와 (작물, 병해충, 변환 구분) 등록 행들을 한 번만 만들어 둔다."""
    intl_codes = {m["kr_code"]: m["intl_code"] for m in load("moa")}
    status = {s["use_id"]: s["parse_status"] for s in load("safe_use_std")}
    found: dict[tuple[str, str], dict] = {}
    for u in load("pesticide_use"):
        drug = found.setdefault(
            (u["product"], u["brand"]), {"id": u["use_id"], "moa": u["moa_code"], "rows": []}
        )
        drug["id"] = min(drug["id"], u["use_id"])
        drug["rows"].append((_pest_crops()[u["pest_id"]], u["pest_id"], status[u["use_id"]]))
    return tuple(
        (Pesticide(d["id"], brand, product, _moa(d["moa"], intl_codes)), tuple(d["rows"]))
        for (product, brand), d in found.items()
    )


def list_crops() -> list[Crop]:
    return [Crop(crop_id, name) for crop_id, name in sorted(_crops().items())]


def list_pesticides(crop_id: int, pest_id: int | None = None) -> list[PesticideEntry]:
    if crop_id not in _crops():
        raise AppError("NOT_FOUND", 404, "작물을 찾을 수 없습니다")
    if pest_id is not None and _pest_crops().get(pest_id) != crop_id:
        # 병해충은 작물별로 나뉘어 있어, 다른 작물의 병해충도 없는 것으로 본다
        raise AppError("NOT_FOUND", 404, "병해충을 찾을 수 없습니다")
    entries = []
    for pesticide, rows in _drugs():
        statuses = [s for c, p, s in rows if c == crop_id and (pest_id is None or p == pest_id)]
        if statuses:
            entries.append(PesticideEntry(pesticide, all(s == "stage" for s in statuses)))
    # 작용기작(없는 약제는 맨 뒤) → 품목명 → 상표명
    entries.sort(
        key=lambda e: (
            e.pesticide.moa is None,
            e.pesticide.moa.label_kr if e.pesticide.moa else "",
            e.pesticide.item_name,
            e.pesticide.name,
        )
    )
    return entries
