# External Call Common Handling Implementation Plan (BE-16)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (project CLAUDE.md: no subagent-driven execution). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One place for what every external HTTP call shares (5-second client, no retry, any transport failure becomes 502 `UPSTREAM_ERROR` with `details.source`, no key in logs), used by `farmmap.py` and `vworld.py` now and by `kma.py` (weather) when it is written.

**Architecture:** New `app/core/upstream.py` with `TIMEOUT_SECONDS`, `new_client()`, `upstream_error(...)` and `get(...)`. `farmmap.py` and `vworld.py` keep their parsing and their call sites; only the duplicated bodies (timeout constant, httpx2 log silencing, the error builder, the client-or-default GET block) become delegations. `field_service._fetch_parcels` builds its shared client through `new_client()` instead of reading `farmmap.TIMEOUT_SECONDS`. Behavior does not change.

**Tech Stack:** Python 3.13, `httpx2` (sync client, `MockTransport` in tests), pytest.

**Spec:** Approved in chat 2026-10-30 (summary above); basis = `팜가디언_아키텍처.md` §8 「공통」 and §1 of `팜가디언_API_명세.md` (`UPSTREAM_ERROR` 502, `details {source, upstream_code?}`, never edited).

## Global Constraints

- `farmmap` and `vworld` behave exactly as before: messages `팜맵 조회에 실패했습니다` and `주소 검색에 실패했습니다`, `details` `{"source": "farmmap"|"vworld"}` plus `upstream_code` when there is one, 5-second timeout, no retry, the same body-reading rules. `tests/test_farmmap_client.py` and `tests/test_vworld_client.py` pass unchanged and are not edited.
- `팜가디언_API_명세.md`, `schema.sql` and `requirements*.txt` do not change; no new dependency.
- The API key is in the request URL. No log line, error message or exception text may contain the URL, the params or the key. The log keeps `source`, `upstream_code` and `cause` (the exception class name) only. `httpx2`'s own request logging stays at WARNING, now set in one place.
- `get` returns the response for **any HTTP status** (callers read the body: Farmmap answers a key error with 403 plus a code, VWorld answers errors inside HTTP 200 or with an HTML 400). Only `httpx2.HTTPError` (timeout, connection failure) becomes 502.
- A client passed in is never closed; the default client is created per call and closed, also when the call fails.
- Files outside my folders that change, for Hyebin's review: `app/farm/infrastructure/integrations/farmmap.py`, `.../vworld.py`, `app/farm/application/field_service.py` (one reference). Minimal edits only; no renames, no reformatting.
- Docs: `팜가디언_아키텍처.md` line 68 (core list) and the §8 「공통」 bullet are updated; no other document.
- Short Korean comments like the surrounding code; ruff line length 100; tests flat in `tests/`; commit messages in English with the session's attribution trailer; do not push; stage explicit paths only (the working tree has an unrelated uncommitted backlog xlsx, `.gitignore` change and an untracked scenario doc). Branch `feat/jh-upstream-common` from `test` at `848443d`.

## Review Focus

- A failing call whose URL carries the key never leaks the key, the URL or the params into the log or the error. (Task 1)
- A client passed in stays open; the default client is closed, also on failure. (Task 1)
- Non-2xx responses come back instead of raising, so Farmmap's 403 gateway error and VWorld's HTML 400 still map as before. (Tasks 1–3, existing client tests)
- The shared client in `field_service` still has the 5-second timeout and the 8-way concurrency is untouched. (Task 2)
- Messages and `details` shape are identical for both sources. (Tasks 2, 3)

---

### Task 0: Branch and commit this plan

- [ ] **Step 1:** `git switch -c feat/jh-upstream-common` (from `test`; unrelated uncommitted and untracked files stay as they are).
- [ ] **Step 2:** `git add docs/dev/2026-10-30-upstream-common-plan.md` / `git commit -m "Add upstream common plan"`.

### Task 1: The common module

**Files:**
- Create: `app/core/upstream.py`
- Create: `tests/test_upstream.py`

**Interfaces:**
- Produces: `TIMEOUT_SECONDS = 5`; `new_client() -> httpx2.Client` (timeout 5 s); `upstream_error(source: str, message: str, upstream_code: str | None = None, *, cause: str | None = None) -> AppError` (`AppError("UPSTREAM_ERROR", 502, message, details)`, `details` has `source` and, only when given, `upstream_code`; logs one WARNING on logger `app.upstream` with `source`, `upstream_code`, `cause`); `get(source: str, message: str, url: str, params: dict, *, client: httpx2.Client | None = None) -> httpx2.Response`.

- [ ] **Step 1: Write the failing tests** in `tests/test_upstream.py` (a `_client(handler)` helper builds `httpx2.Client(transport=httpx2.MockTransport(handler))`, as in `tests/test_vworld_client.py`):
  - `test_get_returns_the_response_and_passes_the_params`: the handler asserts `dict(request.url.params) == {"a": "1", "b": "2"}` and the request URL path, returns `Response(200, text="ok")`; `get("x", "m", "https://example.test/p", {"a": "1", "b": "2"}, client=...)` has `.text == "ok"`.
  - `test_error_statuses_are_returned_not_raised` (parametrize 403, 500): `get(...)` returns a response whose `status_code` is that status.
  - `test_transport_failures_become_502` (parametrize `httpx2.ReadTimeout`, `httpx2.ConnectError`): `AppError` with `code == "UPSTREAM_ERROR"`, `status == 502`, `message == "m"`, `details == {"source": "x"}`.
  - `test_upstream_error_details`: with `upstream_code="30"` the details are `{"source": "x", "upstream_code": "30"}`; without it there is no `upstream_code` key.
  - `test_a_passed_client_stays_open_and_the_default_client_is_closed`: after `get(..., client=c)`, `c.is_closed is False`; with `monkeypatch.setattr(upstream, "new_client", lambda: tracked)`, `tracked.is_closed is True` after a successful `get` and also after one whose handler raises `ConnectError`.
  - `test_new_client_uses_a_five_second_timeout`: `upstream.TIMEOUT_SECONDS == 5` and `new_client().timeout == httpx2.Timeout(5)`.
  - `test_failures_are_logged_without_the_key` (`caplog` at WARNING): a failing `get("x", "m", "https://example.test/p", {"key": "SECRET-KEY-123"}, client=...)` logs text containing `source=x` and `ReadTimeout`, and containing neither `SECRET-KEY-123` nor `example.test`; `upstream_error("x", "m", "30")` logs `upstream_code=30`.
  - `test_httpx2_request_logging_stays_off`: `logging.getLogger("httpx2").getEffectiveLevel() >= logging.WARNING`.
- [ ] **Step 2:** `pytest tests/test_upstream.py -v` → FAIL (`ModuleNotFoundError: app.core.upstream`).
- [ ] **Step 3: Implement** `app/core/upstream.py` to the interface above. `get` uses the passed client or `new_client()` in a `with`, catches `httpx2.HTTPError` and raises `upstream_error(source, message, cause=type(e).__name__) from None` (no exception chaining, the original message can carry the URL). Silence `logging.getLogger("httpx2")` at import with the existing Korean comment about the key in the URL.
- [ ] **Step 4:** `pytest tests/test_upstream.py -v` → all PASS; `ruff check app/core tests/test_upstream.py` clean.
- [ ] **Step 5:** `git add app/core/upstream.py tests/test_upstream.py` / `git commit -m "Add common upstream call handling"`.

### Task 2: Move farmmap and the shared client

**Files:**
- Modify: `app/farm/infrastructure/integrations/farmmap.py`, `app/farm/application/field_service.py`

**Interfaces:**
- Consumes: `upstream.get`, `upstream.upstream_error`, `upstream.new_client`.
- Produces: nothing new. `farmmap.TIMEOUT_SECONDS` is removed (its only user is `field_service`).

- [ ] **Step 1:** Baseline: `pytest tests/test_farmmap_client.py tests/test_farmmap_parser.py tests/test_field_service.py tests/test_fields_api.py tests/test_parcels_api.py -q` → all pass; note the count.
- [ ] **Step 2: Edit `farmmap.py`:** drop `import logging`, the `logging.getLogger("httpx2")...` line with its comment and `TIMEOUT_SECONDS`; add module constants `_SOURCE = "farmmap"` and `_MESSAGE = "팜맵 조회에 실패했습니다"`; make `_upstream_error(upstream_code=None)` return `upstream_error(_SOURCE, _MESSAGE, upstream_code)` (call sites stay as they are); in `_fetch` replace the `try/except httpx2.HTTPError` block with `response = upstream.get(_SOURCE, _MESSAGE, url, params, client=client)`; keep reading the body whatever the status.
- [ ] **Step 3: Edit `field_service.py`:** `httpx2.Client(timeout=farmmap.TIMEOUT_SECONDS)` becomes `upstream.new_client()`; import `upstream` from `app.core`; drop the `import httpx2` if nothing else uses it.
- [ ] **Step 4:** The baseline command → the same count passes; `ruff check app tests` clean.
- [ ] **Step 5:** `git add app/farm/infrastructure/integrations/farmmap.py app/farm/application/field_service.py` / `git commit -m "Use common upstream handling in the Farmmap client"`.

### Task 3: Move vworld

**Files:**
- Modify: `app/farm/infrastructure/integrations/vworld.py`

**Interfaces:** Consumes `upstream.get`, `upstream.upstream_error`.

- [ ] **Step 1:** Baseline: `pytest tests/test_vworld_client.py tests/test_address_search_api.py -q` → all pass; note the count.
- [ ] **Step 2: Edit `vworld.py`** the same way: drop `import logging`, the log line and `TIMEOUT_SECONDS`; constants `_SOURCE = "vworld"` and `_MESSAGE = "주소 검색에 실패했습니다"`; `_upstream_error` delegates; `search_parcels` calls `upstream.get(_SOURCE, _MESSAGE, SEARCH_URL, params, client=client)` instead of its own client block.
- [ ] **Step 3:** The baseline command → the same count passes; `ruff check app tests` clean.
- [ ] **Step 4:** `git add app/farm/infrastructure/integrations/vworld.py` / `git commit -m "Use common upstream handling in the VWorld client"`.

### Task 4: Docs and full verification

**Files:** Modify `docs/dev/팜가디언_아키텍처.md`

- [ ] **Step 1:** Update line 68 (`core/` list) to mention `upstream.py (외부 호출 공통)` and the §8 「공통」 bullet to name `app/core/upstream.py` (`get`, `upstream_error`, `new_client`); change nothing else in that document.
- [ ] **Step 2:** `grep -rn "TIMEOUT_SECONDS" app` → only `app/core/upstream.py`; `grep -rn "getLogger(\"httpx2\")" app` → only `app/core/upstream.py`.
- [ ] **Step 3:** `pytest -q -rs` → every test passes, none skipped; `ruff check .` → `All checks passed!`.
- [ ] **Step 4:** Live check with the real keys through the app (as before: `/addresses/search?keyword=청평리 161-3`, `/parcels` for its PNU, `farmmap.parcel_by_id`), expecting 200 with 1 address, 2 parcels and the parcel found; then one call through a transport that raises `ConnectError` with the real key in the params, expecting 502 `UPSTREAM_ERROR` and a captured log line without the key.
- [ ] **Step 5:** `git add docs/dev/팜가디언_아키텍처.md` / `git commit -m "Document the common upstream handling"`; `git status -sb` shows only the three unrelated files and the branch 5 commits ahead of `origin/test`.
- [ ] **Step 6:** Report: commands and output, the three files of Hyebin's that changed (for her review), that `kma.py` can now use `upstream.get("kma", ...)`, and that push and PR wait for the user's word.
