import functools

from app.catalog.domain.entities import (
    Crop,
    Moa,
    PestCard,
    Pesticide,
    PesticideEntry,
    PestVector,
)
from app.catalog.domain.pest_rules import (
    OCCURRENCE_SOURCES,
    occurrence_text,
    pick_season,
    representative_photo,
)
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


_KIND = {"disease": "병", "insect": "해충"}


@functools.cache
def _pests() -> dict[int, dict]:
    return {p["pest_id"]: p for p in load("pest")}


@functools.cache
def _by_pest(name: str, key: str = "pest_id") -> dict[int, tuple[dict, ...]]:
    grouped: dict[int, list[dict]] = {}
    for row in load(name):
        grouped.setdefault(row[key], []).append(row)
    return {pest_id: tuple(rows) for pest_id, rows in grouped.items()}


def get_pest_card(pest_id: int) -> PestCard | None:
    pest = _pests().get(pest_id)
    if pest is None:
        return None
    photo = representative_photo(_by_pest("pest_photo").get(pest_id, ()))
    season = pick_season(_by_pest("pest_season").get(pest_id, ()))
    vectors = sorted(
        (
            PestVector(
                v["vector_pest_id"],
                _pests()[v["vector_pest_id"]]["name"],
                v["guide_text"],
                v["evidence"],
            )
            for v in _by_pest("virus_vector", "virus_pest_id").get(pest_id, ())
            if v["vector_pest_id"] is not None
        ),
        key=lambda vector: vector.name,
    )
    return PestCard(
        id=pest_id,
        name=pest["name"],
        kind=_KIND.get(pest["kind"]),
        photo_url=photo["url"] if photo else None,
        photo_source=pest["photo_crop"] if photo else None,
        description=pest["symptom"] or None,
        occurrence=occurrence_text(season) if season else None,
        occurrence_source=OCCURRENCE_SOURCES[season["source"]] if season else None,
        vectors=tuple(vectors),
    )
