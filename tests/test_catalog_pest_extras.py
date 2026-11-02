from collections import defaultdict

from app.catalog.application import catalog_service as svc
from app.catalog.domain.entities import PestRef
from app.catalog.domain.pest_rules import pick_season
from app.catalog.infrastructure.static_data import load


def seasons_by_pest():
    found = defaultdict(list)
    for row in load("pest_season"):
        found[row["pest_id"]].append(row)
    return found


def test_months_are_the_chosen_season_rows_months():
    seasons = seasons_by_pest()
    for pest_id, rows in seasons.items():
        assert svc.get_pest_card(pest_id).months == tuple(pick_season(rows)["months"])
    without = next(p["pest_id"] for p in load("pest") if p["pest_id"] not in seasons)

    assert svc.get_pest_card(without).months == ()


def test_is_virus_matches_the_virus_vector_file():
    ids = {p["pest_id"] for p in load("pest") if svc.get_pest_card(p["pest_id"]).is_virus}

    assert ids == {v["virus_pest_id"] for v in load("virus_vector")}


def test_carries_lists_the_viruses_a_vector_carries_sorted_by_name():
    names = {p["pest_id"]: p["name"] for p in load("pest")}
    carried = defaultdict(list)
    for v in load("virus_vector"):
        if v["vector_pest_id"] is not None:
            virus_id = v["virus_pest_id"]
            carried[v["vector_pest_id"]].append(PestRef(virus_id, names[virus_id]))

    assert carried
    for pest in load("pest"):
        expected = tuple(sorted(carried.get(pest["pest_id"], ()), key=lambda ref: ref.name))
        assert svc.get_pest_card(pest["pest_id"]).carries == expected
    virus = next(iter({v["virus_pest_id"] for v in load("virus_vector")}))
    assert svc.get_pest_card(virus).carries == ()  # 바이러스는 매개충이 아니다


def test_pesticide_count_equals_the_pool_size():
    for p in load("pest"):
        pool = svc.list_pesticides(p["crop_id"], p["pest_id"])

        assert svc.get_pest_card(p["pest_id"]).pesticide_count == len(pool)
