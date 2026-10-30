# API Playground Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (project CLAUDE.md: no subagent-driven execution). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One HTML file that walks the 26-step scenario of `팜가디언_사용자_시나리오.md` against the running API, so the backend (and later the frontend) can click through the real flow and see which of the 24 spec APIs work today.

**Architecture:** `docs/dev/api_playground.html`: single file, vanilla JS, no build step, no CDN. A header (API address, health, current user), a left rail with the scenario sections A–F, one panel per section whose numbered cards are the scenario steps (each card says which API it calls), a request log at the bottom, and a coverage panel mirroring the scenario's 「사용한 API 체크 (24개)」 table. At load it reads the server's `/openapi.json` to learn which spec endpoints exist, so the 5 missing ones (split-preview, zones create, `GET`/`PATCH /zones/{id}`, weather) show 「아직 구현 안 됨」 with a fallback, and start working by themselves once the backend has them.

**Tech Stack:** HTML, CSS, vanilla JS (`fetch`, `localStorage`, inline SVG). Verification drives Chrome with the Claude-in-Chrome tools against a local API (uvicorn on the test DB, real Farmmap and VWorld keys) served pages via `python -m http.server`.

**Spec:** Design approved in chat 2026-10-30 (summary above). Flow = `docs/dev/팜가디언_사용자_시나리오.md` (26 steps A–F, 검수 메모 1–5); contract = `docs/dev/팜가디언_API_명세.md` (never edited).

## Global Constraints

- Only the new file `docs/dev/api_playground.html` and this plan are added. No change to `app/`, `schema.sql`, the spec or the scenario doc. The page is a dev tool, not the product frontend (that is React + Vite elsewhere).
- No build, no framework, no external script or stylesheet. The only network targets are the API base URL (default `http://localhost:8000`, editable, kept in `localStorage`) and `photo_url` images from the API data.
- **API data is never put into `innerHTML`.** Build DOM with a helper that sets `textContent` (pest names and descriptions come from an external source; usernames and field names are user input).
- Header `X-User-Id` is sent whenever a user is logged in; the four no-auth calls (`signup`, `login`, `addresses/search`, `parcels`) work without it (scenario 검수 메모 1). `GET /parcels` sends it when logged in so `used_by_field_id` shows 「사용 중」 (step 23).
- `localStorage` keeps only `base`, `userId` and `username`. The password is never stored. Every `localStorage` access is in try/catch.
- Destructive actions (delete field, cancel spray, withdraw) use an inline two-click confirm, not `window.confirm`.
- `request_id` (UUID v4 via `crypto.randomUUID()`) is created once per 「저장」 action and reused on retry (spec §8); success or 「돌아가기」 clears it.
- Order guidance from 검수 메모: crops before zone creation (2); set 정식일 → enter history → confirm 「누락 없음」 last (3); weather is its own card and its failure never touches the judgment card (4); judging does not save a spray, 「살포 기록 저장」 is a separate button (5).
- Korean UI text, English identifiers, short Korean comments. Commit messages in English with the session's attribution trailer; do not push; stage explicit paths only (the working tree has an unrelated uncommitted backlog xlsx and `.gitignore` change). Branch `feat/jh-api-playground` from `test`.

## Review Focus

- Text from the API (pest descriptions, names with `<`/`&`) shows as text, never as markup. (Tasks 1, 4)
- Server off or wrong address, and CORS refusal: the page says what is wrong and how to fix it (start the API, serve the page on an allowed origin) instead of failing silently. (Task 1)
- Double-click on 가입 and 「살포 기록 저장」: buttons lock while a request is in flight; a retry reuses the same `request_id`; the log shows 201 for the first save and 200 for the replay. (Tasks 2, 4)
- Endpoints missing on the server degrade to a clear 「아직 구현 안 됨」 card with the fallback, and an endpoint that exists is called normally with no page edit. (Tasks 1, 3, 4, 5)
- A deleted or unknown user (after step 25, or a stale stored id) gives 401: the page clears the stored id and shows the login card. (Tasks 1, 5)

---

### Task 0: Branch and commit this plan

- [ ] **Step 1:** `git switch -c feat/jh-api-playground` (from `test`; unrelated uncommitted files stay uncommitted).
- [ ] **Step 2:** `git add docs/dev/2026-10-30-api-playground-plan.md` / `git commit -m "Add API playground plan"`.

### Task 1: Shell, helpers, coverage panel

**Files:**
- Create: `docs/dev/api_playground.html`

**Interfaces (all in the one script; later tasks only add sections):**
- Produces `api(method, path, {query, body, auth = true}) -> Promise<{ok, status, ms, data, error}>`: never throws. Network or CORS failure gives `status: 0`, `error: {code: "NETWORK", message}` with a hint text; a non-JSON body becomes `error: {code: "NON_JSON", message: <first 200 chars>}`; 204 gives `data: null`. Every call is appended to the log (time, method path, status, ms, expandable request/response JSON, red for `error.code`) and, when it matches a spec endpoint, updates the coverage panel. A 401 clears the stored user and shows a login hint.
- Produces `h(tag, attrs, ...kids)` (strings become text nodes), `note(box, kind, text)`, `twoStep(button, label, onConfirm)`, `vBadge(verdict)` (`OK` 가능, `CAUTION` 주의, `BLOCKED` 불가, `NEEDS_CHECK` 확인 필요, with colors; spec §2), `drawGeometry(svg, layers[{geometry, fill, stroke, label}])` (one bbox over all layers, y axis flipped, `fill-rule: evenodd`), `state` plus `persist()`.
- Produces `SPEC_APIS` (the 24 rows of the scenario's table: method, path, step numbers), `implemented(method, path) -> boolean` from `/openapi.json` (path params normalised to `{}`), `section(id, title, steps[{no, title, apis, render(box)}])` and `card(no, title, apis)` (shows 「이 단계가 부르는 API」 and a 「아직 구현 안 됨」 banner when any listed API is missing), `pickZone(box, onPick)` placeholder replaced in Task 3.

- [ ] **Step 1:** Start the servers (background): the API with `DATABASE_URL` set to the test DB URL from `.env` (read it without printing) on port 8000, and `python -m http.server 3000` in `docs/dev`. Check `.env`'s `CORS_ORIGINS` contains `http://localhost:3000`. Expected: `curl localhost:8000/health` → `{"status":"ok"}`.
- [ ] **Step 2:** Write the shell: layout (header, left rail A–F, panel, bottom log, coverage panel with 24 rows and a counter 「N/24 호출 성공 · M 미구현」), CSS with light and dark colors and a phone-width layout, the helpers above, the openapi probe at load, and empty sections A–F whose cards list their APIs.
- [ ] **Step 3: Verify in Chrome** (open `http://localhost:3000/api_playground.html`): the health badge says connected; the coverage panel marks exactly the 5 missing endpoints 미구현 (19 present); `read_console_messages` pattern `error|Uncaught` is empty. Then set the API address to `http://localhost:9`: the page shows the NETWORK hint (no silent failure) and recovers when the address is set back. In the console: `h("div", {}, "<img src=x onerror=alert(1)>")` renders as text.
- [ ] **Step 4:** `git add docs/dev/api_playground.html` / `git commit -m "Add API playground shell"`.

### Task 2: A. 가입과 첫 밭 (steps 1–4) and 26. 로그인

**Files:** Modify `docs/dev/api_playground.html`

**Interfaces:** Consumes Task 1's helpers. Produces `parcelPicker(box, {onSelect})` (address search + parcel list + map, reused by step 23 in Task 5) returning the selected `farmmap_id` list, and `renderField(box, field)` (name, area, SVG of the geometry, zone list), reused by Tasks 3 and 5.

- [ ] **Step 1: Cards 1–2** (`GET /addresses/search`, `GET /parcels`, both without login): keyword box and search with paging (`page`, 10 per page, total); clicking a result loads its parcels as cards with checkboxes (max 20): `lnm`, `land_use`, `area_m2`, `matches_query` badge, 「사용 중」 and disabled when `used_by_field_id` is set, plus an SVG map of all parcels with the selected ones highlighted. Spec 422/502 messages are shown by `error.code`.
- [ ] **Step 2: Card 3** (`POST /auth/signup`): username, password, field name inputs, button locked while in flight. On 201 store id and username, show the new field with `renderField`, move on. 409 `USERNAME_TAKEN`, 422 (per-field `loc` messages), 502 `UPSTREAM_ERROR` each get a clear message.
- [ ] **Step 3: Card 4** (`GET /me`): shows `onboarded`; when false, a hint to go on to section B. Card 26 (「다음 해 재방문」, `POST /auth/login`) lives in this section with a username/password form.
- [ ] **Step 4: Verify in Chrome** with the real keys: search `청평리 161-3`, pick the PNU, select the two parcels, sign up as `pg_a1` (field 「뒷밭」) → header shows the new user, the field's SVG is drawn, step 4 says onboarded false. A second signup with the same name shows `USERNAME_TAKEN`; logging out and logging in again as `pg_a1` works; a double-click on 가입 produces exactly one `POST /auth/signup` in the log. Console clean.
- [ ] **Step 5:** `git add docs/dev/api_playground.html` / `git commit -m "Add playground section A: signup and first field"`.

### Task 3: B. 구역 나누기·온보딩 (steps 5–11)

**Files:** Modify `docs/dev/api_playground.html`

**Interfaces:** Produces `pickZone(box, onPick)` (zones from `GET /fields` flattened, or a typed zone id) and the state `zoneId`, used by Tasks 4 and 5; `sqlZone(fieldId, userId, cropId)` and `sqlConfirm(zoneId, plantedAt)` returning the SQL text shown with a 「복사」 button.

- [ ] **Step 1: Cards 5–7:** `GET /crops` list (feeds the crop selects); `POST /fields/{id}/split-preview` with direction (`crosswise`/`lengthwise`) and ratios (`1,1,1` style), drawing the `SplitPiece`s with areas, repeatable; `POST /fields/{id}/zones` with one name/crop/정식일 row per ratio. When these two endpoints are not implemented the cards show the banner and the fallback: 「구역 ID 직접 입력」 plus the SQL from `sqlZone` (`INSERT INTO zone (field_id, user_id, name, crop_id, geom) SELECT id, user_id, '구역', <crop>, geom FROM field WHERE id = <field id>`), for `psql` on the dev DB with `PGCLIENTENCODING=UTF8`.
- [ ] **Step 2: Cards 8–9:** with `pickZone`, past spray input (`POST /zones/{id}/sprays`): pesticide filtered by typing a name over `GET /pesticides?crop_id=` (the zone's crop), `sprayed_on` (not in the future), source `manual`, fresh `request_id` per save; history list (`GET /zones/{id}/sprays`) with a two-click cancel (`DELETE .../{sid}`).
- [ ] **Step 3: Cards 10–11:** `PATCH /zones/{id}` form (`planted_at`, `history_confirmed`) with the order hint (정식일 → 이력 → 누락 없음 last); when missing, the banner and `sqlConfirm`. `POST /me/onboarding` shows the 422 `ONBOARDING_INCOMPLETE` `details` (`zone_count`, `unconfirmed_zone_ids`) in words.
- [ ] **Step 4: Verify in Chrome** as `pg_a1`: cards 6–7 show the banner (endpoints absent). Run the displayed `sqlZone` text against the test DB with a Python/psycopg one-liner (this proves the snippet) and refresh: the zone appears. Save two sprays (two different pesticides, dates in October), see both in the history, cancel one (two clicks), re-add it. `sqlConfirm` text run on the test DB, then card 11 succeeds; before it, card 11 shows 422 with `zone_count` 1 and the zone id. Console clean.
- [ ] **Step 5:** `git add docs/dev/api_playground.html` / `git commit -m "Add playground section B: zones and onboarding"`.

### Task 4: C. 홈 (steps 12–13) and D. 병해충·약제 판정 (steps 14–20)

**Files:** Modify `docs/dev/api_playground.html`

**Interfaces:** Consumes `renderField`, `pickZone`, `vBadge`. Produces `judgeCard` state `{zone, pest, pesticide}`.

- [ ] **Step 1: Cards 12–13:** `GET /fields` as home cards (zone summaries with `last_spray` and `last_judgment`, 「기록 없음」 when null); `GET /zones/{id}` card showing `rotation` as bars (`count/total` per `moa.label_kr`, `window_start`) and `recent_judgments`; banner when absent.
- [ ] **Step 2: Cards 14–17:** symptom-part chips (`GET /crops/{id}/symptom-parts` for the zone's crop) → pest cards from `GET /pests/candidates` (photo, kind, `description`, `occurrence`, vectors as chips that switch the chosen pest to the vector, optional) or name search (`GET /pests?q=`); pesticide list from `GET /pesticides?crop_id=&pest_id=` with the `at_planting_only` ones in their own group, `moa.label_kr` shown, and a 「병해충 지정 안 함」 option.
- [ ] **Step 3: Card 18:** optional `apply_date`, button `POST /zones/{id}/judgments`; result view: `vBadge` for the verdict, four check cards in the spec order (registration, timing, count, moa) with `message`, `facts` as a key list and `evidence.source_text` plus 「데이터 조회일 data_asof」, `notices`, alternatives (clicking one re-judges with it), and a 「농업기술센터 문의」 banner when `show_extension_office`. A line states that judging saved no spray (검수 메모 5).
- [ ] **Step 4: Cards 19–20:** weather as its own card (`GET /zones/{id}/weather`, 24 hourly rows: `pty` word, `pcp` text, `pop`), its error or absence never alters the judgment card. 「살포 기록 저장」: one `request_id` per action, button locked in flight, a 「두 번 눌러 보기」 control that sends the same body and id twice (expect 201 then 200 with the same record); 409 `DUPLICATE_SPRAY` offers 「기존 기록 확인 / 별도 살포로 저장 / 돌아가기」 (the second sends the same id with `allow_duplicate: true`).
- [ ] **Step 5: Verify in Chrome** on `pg_a1`'s zone: choose 「잎」 (or the first part), pick a pest and a drug, judge: the verdict badge, four checks and evidence render; with the zone unconfirmed the count and moa cards say 확인 필요. Pick an unregistered drug with a pest: alternatives appear after the zone is confirmed (SQL from Task 3). Save a spray twice with 「두 번 눌러 보기」: log shows 201 then 200, history has one new record; repeat the same drug/date: the 409 flow works. Weather and cards 12–13 show the banner. A pest description containing `<b>x</b>` stays text (inject through a mocked row only if the data has none; otherwise rely on Task 1's check). Console clean.
- [ ] **Step 6:** `git add docs/dev/api_playground.html` / `git commit -m "Add playground sections C and D: home and judgment"`.

### Task 5: E. 조회수정 (steps 21–22) and F. 밭 추가·정리 (steps 23–25)

**Files:** Modify `docs/dev/api_playground.html`

**Interfaces:** Consumes `parcelPicker`, `renderField`, `pickZone`, `twoStep`.

- [ ] **Step 1: Cards 21–22:** history with paging (`limit`, `offset`, `total`) and two-click cancel; zone edit form for 이름, 작물, 정식일 (`PATCH /zones/{id}`, banner and SQL fallback when absent; text explains that a crop change starts a new crop cycle and clears 「누락 없음」).
- [ ] **Step 2: Cards 23–25:** add a field with `parcelPicker` (`used_by_field_id` shows 「사용 중」), `POST /fields` (409 `PARCEL_ALREADY_USED` lists `details.farmmap_ids`), two-click delete of a field (`DELETE /fields/{id}`), two-click withdrawal (`DELETE /me`) after which the stored user is cleared and the next call's 401 shows the login card.
- [ ] **Step 3: Verify in Chrome** on `pg_a1`: add a second field with a different parcel, delete it (two clicks), try to add a field with an already-used parcel (409 shown with ids), page the history with `limit=1`. Withdraw: the user is cleared, the login card appears, `GET /me` with the old id in the log is 401, and the test DB has no `pg_%` rows left for that user. Console clean.
- [ ] **Step 4:** `git add docs/dev/api_playground.html` / `git commit -m "Add playground sections E and F: edit and cleanup"`.

### Task 6: Full scenario run and wrap-up

- [ ] **Step 1:** Fresh browser state (clear the page's `localStorage`), run steps 1–26 of the scenario in order against the live API. Expected: the coverage panel ends at 19 ✔ and 5 미구현 (unless the backend gained endpoints meanwhile, in which case the new ones are exercised), no page error in the console, and every missing endpoint step showed its banner and fallback.
- [ ] **Step 2:** Clean the test DB (`DELETE FROM users WHERE username LIKE 'pg_%'`, cascades), stop both servers, confirm `pytest -q` still passes (1024) and `git status` shows only the two unrelated files plus the branch's commits.
- [ ] **Step 3:** Report to the user: how to run it (`python -m http.server 3000` in `docs/dev`, API on 8000, open `http://localhost:3000/api_playground.html`), what each fallback needs (SQL via `psql`), what was verified and what was not, and that push and PR wait for their word.
