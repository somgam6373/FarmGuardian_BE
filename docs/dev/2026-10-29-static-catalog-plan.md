# Static Catalog Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (project CLAUDE.md: no subagent-driven execution). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put the 12 delivered reference JSON files in the repo, read them into memory through one cached function, pin their shape with tests, and make `schema.sql` and the docs say the catalog is not in the database.

**Architecture:** `app/catalog/data/*.json` (verbatim) + `app/catalog/infrastructure/static_data.py` (`load(name)`, whitelist, `functools.cache`). Data checks are plain pytest tables over the loaded rows, no database. `schema.sql` loses the 9 catalog tables and the foreign keys into them; `crop` stays.

**Tech Stack:** Python 3.13 stdlib (`json`, `pathlib`, `functools`), pytest, psycopg (only for the throwaway schema check in Task 3).

**Spec:** `docs/dev/2026-10-29-static-catalog-design.md` (approved in chat 2026-10-29)

## Global Constraints

- No new dependency. JSON is read with `Path.read_text(encoding="utf-8")` — never the Windows default (cp949), the files are Korean UTF-8 without BOM.
- Data files are copied byte for byte from `C:\Users\USER\Desktop\팜가디언 json\`; only these 12 names: `crop`, `moa`, `ingredient`, `pest`, `pest_alias`, `pest_photo`, `pest_season`, `pesticide_use`, `safe_use_std`, `use_ingredient`, `rotation_rule`, `virus_vector`. The 4 seed files (`app_user`, `field`, `zone`, `spray_log`) are not copied.
- ③ is summed by item name; `item_name` = `pesticide_use.product`. A pesticide = (`product`, `brand`) pair; its id = the smallest `use_id` of the pair.
- `crop` stays in the database; `crop.json` ids and names must equal the table's (1 감자, 2 배추, 3 토마토).
- Code and identifiers in English; short Korean comments as in `app/core`. Ruff line length 100, rules E/F/I. Tests are flat files in `tests/`.
- Commit messages in English. Do not push (the user opens the PR).

## Review Focus

- `load("../crop")`, `load("crop.json")`, `load("Crop")`, `load("")` cannot read outside the whitelist → `ValueError`. (Task 1)
- Korean text survives on a Korean-locale Windows (no cp949 decoding): `load("crop")` names equal `감자, 배추, 토마토`. (Task 1)
- `ok` rows always have `phi_days` and `max_count`; `stage`, `no_std`, `failed` rows have NULL `phi_days`. The judgment relies on this. (Task 2)
- A re-delivered JSON with renumbered `use_id`s silently moves every pesticide id and breaks stored `spray_log` rows → pinned (`use_id` → product, brand) samples. (Task 2)
- Compound action-group codes (`13+22b`) are not rows of `moa`; each part must be. (Task 2)
- `schema.sql` still applies on an empty PostGIS database after the cut. (Task 3)

---

### Task 0: Commit the design and this plan

- [ ] **Step 1:** `git add docs/dev/2026-10-29-static-catalog-design.md docs/dev/2026-10-29-static-catalog-plan.md` / `git commit -m "Add static catalog design and plan"`

### Task 1: Loader and data files

**Files:**
- Create: `app/catalog/__init__.py`, `app/catalog/infrastructure/__init__.py` (both empty, like `app/farm`), `app/catalog/infrastructure/static_data.py`, `app/catalog/data/<12 names>.json`
- Test: `tests/test_catalog_data.py`

**Interfaces:**
- Produces: `load(name: str) -> list[dict]` in `app.catalog.infrastructure.static_data`. Whitelisted names only (the 12 above), else `ValueError`. Cached: two calls return the same object. Callers must not modify the result.

- [ ] **Step 1: Write the failing tests** in `tests/test_catalog_data.py`
```python
import pytest

from app.catalog.infrastructure.static_data import load

COUNTS = {
    "crop": 3, "moa": 70, "ingredient": 216, "pest": 129, "pest_alias": 16, "pest_photo": 185,
    "pest_season": 51, "pesticide_use": 4133, "safe_use_std": 4133, "use_ingredient": 4949,
    "rotation_rule": 6, "virus_vector": 12,
}


@pytest.mark.parametrize("name,count", COUNTS.items())
def test_row_counts(name, count):
    assert len(load(name)) == count


@pytest.mark.parametrize(
    "name", ["app_user", "field", "zone", "spray_log", "", "../crop", "crop.json", "Crop"]
)
def test_unknown_name_is_rejected(name):
    with pytest.raises(ValueError):
        load(name)


def test_korean_text_is_decoded():
    assert [c["name"] for c in load("crop")] == ["감자", "배추", "토마토"]


def test_load_is_cached():
    assert load("crop") is load("crop")
```
- [ ] **Step 2: Run** `.venv\Scripts\python -m pytest tests\test_catalog_data.py -q` — Expected: collection ERROR `No module named 'app.catalog'`.
- [ ] **Step 3: Implement `load`** in `static_data.py`: `DATA_DIR = Path(__file__).resolve().parents[1] / "data"`; a module-level frozenset of the 12 names; `@functools.cache def load(name: str) -> list[dict]` raising `ValueError(f"unknown catalog file: {name!r}")` for any other name, otherwise `json.loads((DATA_DIR / f"{name}.json").read_text(encoding="utf-8"))`. Short Korean comment: the result is shared, do not modify.
- [ ] **Step 4: Copy the 12 files** from `C:\Users\USER\Desktop\팜가디언 json\` to `app/catalog/data/` with `cp` (create the folder first). Verify byte identity: `sha256sum` of source and destination agree for all 12, and `ls app/catalog/data` shows exactly 12 files.
- [ ] **Step 5: Run** the step 2 command — Expected: all pass (12 counts + 8 rejections + 2 = 22 passed). Then `.venv\Scripts\python -m pytest -q` — all pass.
- [ ] **Step 6: Commit** `git add app/catalog tests/test_catalog_data.py` / `git commit -m "Add static catalog data and loader"`

### Task 2: Data checks

**Files:**
- Modify: `tests/test_catalog_data.py`

**Interfaces:**
- Consumes: `load` (Task 1), the `db` fixture (`tests/conftest.py`, skips without `TEST_DATABASE_URL`).

- [ ] **Step 1: Write the tests** (append; add `from collections import Counter` and `from sqlalchemy import text` to the imports). The only new logic is the helper, so it gets its own failing test first; the rest characterize the delivered data and pass on first run.
```python
def dangling(rows, key, valid):
    """Values of `key` (ignoring None) that are not in `valid`."""
    ...  # Step 3

def test_dangling_ignores_none_and_reports_missing():
    assert dangling([{"a": 1}, {"a": 9}, {"a": None}], "a", {1}) == {9}

ID_KEYS = {
    "crop": "crop_id", "moa": "moa_id", "ingredient": "ingredient_id", "pest": "pest_id",
    "pest_alias": "alias_id", "pest_photo": "photo_id", "pest_season": "season_id",
    "pesticide_use": "use_id", "safe_use_std": "use_id", "rotation_rule": "rule_id",
}

@pytest.mark.parametrize("name,key", ID_KEYS.items())
def test_ids_are_unique(name, key):
    rows = load(name)
    assert len({r[key] for r in rows}) == len(rows)

def test_use_ids_run_1_to_n_in_both_use_files():
    expected = set(range(1, 4134))
    assert {r["use_id"] for r in load("pesticide_use")} == expected
    assert {r["use_id"] for r in load("safe_use_std")} == expected

REFERENCES = [
    ("use_ingredient", "use_id", "pesticide_use", "use_id"),
    ("use_ingredient", "ingredient_id", "ingredient", "ingredient_id"),
    ("ingredient", "moa_id", "moa", "moa_id"),
    ("pesticide_use", "pest_id", "pest", "pest_id"),
    ("pest", "crop_id", "crop", "crop_id"),
    ("pest_alias", "pest_id", "pest", "pest_id"),
    ("pest_photo", "pest_id", "pest", "pest_id"),
    ("pest_season", "pest_id", "pest", "pest_id"),
    ("virus_vector", "virus_pest_id", "pest", "pest_id"),
    ("virus_vector", "vector_pest_id", "pest", "pest_id"),
]

@pytest.mark.parametrize("child,key,parent,parent_key", REFERENCES)
def test_references_resolve(child, key, parent, parent_key):
    valid = {r[parent_key] for r in load(parent)}
    assert dangling(load(child), key, valid) == set()

def test_every_use_has_one_or_two_ingredients():
    per_use = Counter(r["use_id"] for r in load("use_ingredient"))
    assert set(per_use) == set(range(1, 4134))
    assert Counter(per_use.values()) == {1: 3317, 2: 816}

def test_parse_status_and_null_rules():
    rows = load("safe_use_std")
    assert Counter(r["parse_status"] for r in rows) == {"ok": 3531, "stage": 554, "no_std": 41, "failed": 7}
    assert all(r["phi_days"] is not None and r["max_count"] is not None
               for r in rows if r["parse_status"] == "ok")
    assert Counter(r["parse_status"] for r in rows if r["phi_days"] is None) == {"stage": 554, "no_std": 41, "failed": 6}
    assert Counter(r["parse_status"] for r in rows if r["max_count"] is None) == {"no_std": 41, "failed": 1}
    assert {r["base_date"] for r in rows} == {"2026-10-05"}

def test_moa_codes_resolve_part_by_part():
    kr = {m["kr_code"] for m in load("moa")}
    codes = [u["moa_code"] for u in load("pesticide_use")]
    assert sum(1 for c in codes if not c) == 17           # 계열 코드가 없는 줄 (④ NEEDS_CHECK)
    assert all(set(c.split("+")) <= kr for c in codes if c)   # 복합 계열은 성분별로 풀린다

def test_known_gaps_are_pinned():
    assert sum(1 for i in load("ingredient") if i["moa_id"] is None) == 5
    assert sum(1 for v in load("virus_vector") if v["vector_pest_id"] is None) == 1

SAMPLES = [  # use_id가 재번호된 JSON이 다시 오면 약제 id가 통째로 밀린다 — 여기서 잡는다
    (1, "아미설브롬 입상수화제", "엑사이도"),
    (1000, "메탈락실엠 입제", "리도밀골드"),
    (2500, "트리플록시스트로빈 액상수화제", "프린트"),
    (4133, "피리다클로메틸 액상수화제", "알투도"),
]

def test_pesticide_identity_is_stable():
    uses = {u["use_id"]: u for u in load("pesticide_use")}
    for use_id, product, brand in SAMPLES:
        assert (uses[use_id]["product"], uses[use_id]["brand"]) == (product, brand)
    assert len({u["product"] for u in uses.values()}) == 652
    assert len({(u["product"], u["brand"]) for u in uses.values()}) == 1363

def test_crop_json_matches_the_crop_table(db):
    rows = db.execute(text("SELECT id, name FROM crop ORDER BY id")).all()
    assert [tuple(r) for r in rows] == [(c["crop_id"], c["name"]) for c in load("crop")]
```
- [ ] **Step 2: Run** `.venv\Scripts\python -m pytest tests\test_catalog_data.py -q` — Expected: FAIL in `test_dangling_ignores_none_and_reports_missing` (the stub returns `None`); the data tests already pass.
- [ ] **Step 3: Implement `dangling`** in the test file: set of non-None values of `key` minus `set(valid)`.
- [ ] **Step 4: Run** the same command — Expected: all pass (the DB test passes with `TEST_DATABASE_URL` set). Keep every line ≤ 100 characters (wrap the long `Counter` assertions); `.venv\Scripts\ruff check .` clean.
- [ ] **Step 5: Mutation check.** Temporarily change one `crop_id` in `app/catalog/data/pest.json` to `99`, run the file — Expected: `test_references_resolve[pest-crop_id-crop-crop_id]` FAILS; restore with `git checkout -- app/catalog/data/pest.json`; run again — all pass.
- [ ] **Step 6: Commit** `git add tests/test_catalog_data.py` / `git commit -m "Add static catalog data checks"`

### Task 3: Cut the catalog tables from `schema.sql`

**Files:**
- Modify: `schema.sql`
- Test: `tests/test_schema_sql.py`

- [ ] **Step 1: Write the failing tests** in `tests/test_schema_sql.py`
```python
import re
from pathlib import Path

SCHEMA = (Path(__file__).resolve().parents[1] / "schema.sql").read_text(encoding="utf-8")


def test_only_user_data_tables_and_crop_remain():
    assert set(re.findall(r"CREATE TABLE (\w+)", SCHEMA)) == {
        "users", "crop", "field", "field_parcel", "zone", "spray_log", "judgment",
    }


def test_no_foreign_key_points_into_static_data():
    assert not re.search(r"REFERENCES\s+(pesticide|pest|moa|registration)\b", SCHEMA)
```
- [ ] **Step 2: Run** `.venv\Scripts\python -m pytest tests\test_schema_sql.py -q` — Expected: both FAIL (the 9 catalog tables and 3 foreign keys exist).
- [ ] **Step 3: Edit `schema.sql`.** Delete `moa`, `pesticide` (+ its index), `pest`, `pest_info`, `pest_photo` (+ index), `pest_symptom` (+ index), `pest_occurrence` (+ index), `pest_vector`, `registration` (+ 2 indexes). Keep `crop` and its seed `INSERT`. Change the section comment above `crop` to say: only `crop` is in the database (`zone.crop_id` references it, ids and names equal `app/catalog/data/crop.json`); the rest of the reference data is static JSON in `app/catalog/data/`. `spray_log.pesticide_id`, `judgment.pest_id` and `judgment.pesticide_id` stay (same types and nullability) without `REFERENCES`, with a comment that they hold static-data ids. Update the header's 근거 line to also cite `2026-10-29-static-catalog-design.md`.
- [ ] **Step 4: Run** the step 2 command — Expected: `2 passed`.
- [ ] **Step 5: Prove it applies.** Write `C:\Users\USER\AppData\Local\Temp\claude\C--Users-USER-Desktop-FarmGuardian\e5e0b647-9b92-4ea0-9bc5-867dbdc0a4cc\scratchpad\check_schema.py` (not in the repo): take `TEST_DATABASE_URL` from `.env`, connect with `psycopg` (autocommit) to the same server's `postgres` database, `CREATE DATABASE fg_schema_check_tmp ENCODING 'UTF8' TEMPLATE template0`, connect to it, run the whole `schema.sql` text in one `execute`, print the sorted base-table names, always `DROP DATABASE fg_schema_check_tmp` in `finally` (this exact name only). Never print the URL. Run it with `.venv\Scripts\python -I` — Expected: the 7 tables above plus `spatial_ref_sys`, no error, and `fg_schema_check_tmp` is gone afterwards.
- [ ] **Step 6: Full suite** `.venv\Scripts\python -m pytest -q` and `.venv\Scripts\ruff check .` — all pass. (The existing dev and test databases still have the old tables; that is harmless, nothing reads them. The user recreates them later.)
- [ ] **Step 7: Commit** `git add schema.sql tests/test_schema_sql.py` / `git commit -m "Remove catalog tables from schema.sql"`

### Task 4: Documents

**Files:**
- Modify: `docs/dev/팜가디언_아키텍처.md`, `docs/dev/팜가디언_역할분담_일정.md`

No test. Edit with `Edit`, keep the document's Korean style, change nothing else.

- [ ] **Step 1: Architecture §2 / §3 / §4.**
  - 원천 row (the `약제·병해충 원천` line in §2): replace the Excel → JSON → DB text with: 팀의 데이터 담당이 전달한 정적 JSON 12개(`app/catalog/data/`, 기준일 2026-10-05)를 저장소에 커밋하고 서버가 메모리로 읽는다, DB에 적재하지 않는다 (2026-10-29 결정, §8), PSIS·NCPMS API는 호출하지 않는다.
  - §3 diagram line `엑셀 7개 → JSON ── catalog 적재 (수동 실행) ──┘`: becomes `정적 JSON 12개 (app/catalog/data) ── catalog가 메모리로 읽음` without the connector to the DB box.
  - §4 tree, `catalog/` block: `infrastructure/ models.py` and `ingest/ xlsx_to_json.py, load.py, data/*.json` become `infrastructure/ static_data.py (JSON을 메모리로 읽기)` and `data/ *.json (정적 참고 데이터 12개)`. In the layer rules, `infrastructure` line: `적재 스크립트` → `정적 데이터 읽기`.
- [ ] **Step 2: Architecture §5.** Remove the `pest`, `pest_info`, `pest_symptom`, `pest_vector`, `moa`, `pesticide`, `registration` entries from the schema block; `crop(id, name)` with `UNIQUE(name)`, 3 fixed rows, ids equal `crop.json`; in `spray_log` and `judgment` note that `pesticide_id` / `pest_id` are static-data ids without a foreign key. Remove `registration(...)` and `pesticide(item_name)` from the index list. Replace the intro sentence about Excel/PSIS fields and the bullets that describe catalog tables (`①등록 = registration 행…`, the `③` join on `pesticide.item_name`, `④` on `moa.label_kr`, the 병해충 이름 연결 and 매개충 bullets, and the whole 「엑셀 적재에 따른 스키마 조정」 block) with bullets stating: the input of ①②③ comes from the static `pesticide_use` + `safe_use_std` rows, the conversion to judgment inputs is decided in the BE-38/39 design; rows whose numbers could not be read (`stage`, `no_std`, `failed`) have NULL values and keep their raw text for `NEEDS_CHECK`; ③ counts `spray_log` rows whose pesticide resolves to the same `product` (item name) with `sprayed_on >= planted_at`, in the application; ④ compares action groups from the static `moa`; **pesticide id = smallest `use_id` of the (`product`, `brand`) pair, so `use_id`s must never be renumbered — updates append only**. Keep the `planted_at`, `history_confirmed`, geometry and snapshot bullets.
- [ ] **Step 3: Architecture §8.** Replace the `### 데이터 적재 (엑셀 → JSON → DB …)` section with `### 정적 참고 데이터 (catalog/data/*.json)`: the 2026-10-29 decision and why (changes rarely, no loader, tests need no DB); the 12-file table with row counts and roles (from the design doc); how it is read (`static_data.load(name)`, whitelist, cached, shared and read-only); the pesticide identity and `use_id` append-only rule; the checks in `tests/test_catalog_data.py`; the 4 seed files are not part of it. Update the external-sources table row `약·병해충 데이터` (path `catalog/infrastructure/static_data.py`, no command, no external call) and the §9 test bullet 「데이터 적재 (테스트 DB)」 → 「정적 데이터 검증 (DB 없음): 행 수, id 유일성, 참조 정합성」. Leave the §10 미결 notes and the demo-data bullet as they are.
- [ ] **Step 4: Role doc.** In the `catalog` row replace `엑셀 → JSON → DB 적재` with `정적 JSON 읽기 (app/catalog/data)`.
- [ ] **Step 5:** `grep -n "ingest\|xlsx_to_json\|load\.py" docs/dev/팜가디언_아키텍처.md` — Expected: no match. `git diff --stat` shows only the two docs.
- [ ] **Step 6: Commit** `git add docs/dev/팜가디언_아키텍처.md docs/dev/팜가디언_역할분담_일정.md` / `git commit -m "Update docs for static catalog data"`

### Task 5: Final verification

- [ ] **Step 1:** `.venv\Scripts\python -m pytest -q -rs` and `.venv\Scripts\ruff check .` — Expected: all pass, `All checks passed!`.
- [ ] **Step 2:** `git status -sb` clean, `git log --oneline origin/test..HEAD` lists the 5 commits (design/plan, loader, checks, schema, docs). Do not push.
- [ ] **Step 3:** Tell the user: the PR description must say everyone recreates their dev and test databases from `schema.sql` (not required for tests to pass); backlog rows BE-31 … 35 are obsolete (Excel file, edited by the user); open questions from the design remain (ingredient basis, the data owner's SQL).
