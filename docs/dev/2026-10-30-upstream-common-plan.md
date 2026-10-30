# External Call Common Handling Implementation Plan (BE-16)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (project CLAUDE.md: no subagent-driven execution). Steps use checkbox (`- [ ]`) syntax for tracking.

> **Scope change (2026-10-30, user rule): Hyebin's files are never modified.** The first version of this plan also moved `farmmap.py`, `vworld.py` and one line of `field_service.py` onto the new module. That was implemented once on the unpushed branch and reverted before any push; those two tasks are dropped. The module below stays for **new** external calls (weather `kma.py`); Hyebin's clients keep their own copy of the same rules.

**Goal:** One place for what every external HTTP call shares (5-second client, no retry, any transport failure becomes 502 `UPSTREAM_ERROR` with `details.source`, no key in logs), ready for `kma.py` (weather) when the key arrives.

**Architecture:** New `app/core/upstream.py` with `TIMEOUT_SECONDS`, `new_client()`, `upstream_error(...)` and `get(...)`. Nothing else in `app/` changes.

**Tech Stack:** Python 3.13, `httpx2` (sync client, `MockTransport` in tests), pytest.

**Spec:** Chat 2026-10-30; basis = `팜가디언_아키텍처.md` §8 「공통」 and §1 of `팜가디언_API_명세.md` (`UPSTREAM_ERROR` 502, `details {source, upstream_code?}`, never edited).

## Global Constraints

- **No file of Hyebin's is touched, not even for a one-line reference** (`app/farm/**` except `zone_reader.py`, which I created, and her tests and design documents). Everything is checked with `git diff origin/test -- app/farm` showing nothing.
- `팜가디언_API_명세.md`, `schema.sql` and `requirements*.txt` do not change; no new dependency.
- The API key is in the request URL. No log line, error message or exception text may contain the URL, the params or the key. The log keeps `source`, `upstream_code` and `cause` (the exception class name) only. `httpx2`'s own request logging stays at WARNING, set once here.
- `get` returns the response for **any HTTP status** (callers read the body); only `httpx2.HTTPError` (timeout, connection failure) becomes 502.
- A client passed in is never closed; the default client is created per call and closed, also when the call fails.
- Docs: `팜가디언_아키텍처.md` line 68 (core list) and the §8 「공통」 bullet describe the module; nothing else.
- Short Korean comments; ruff line length 100; tests flat in `tests/`; commit messages in English with the session's attribution trailer; do not push; stage explicit paths only (the working tree has an unrelated uncommitted backlog xlsx, `.gitignore` change and an untracked scenario doc). Branch `feat/jh-upstream-common` from `test` at `848443d`.

## Review Focus

- A failing call whose URL carries the key never leaks the key, the URL or the params into the log or the error. (Task 1)
- A client passed in stays open; the default client is closed, also on failure. (Task 1)
- Non-2xx responses come back instead of raising. (Task 1)

---

### Task 0: Branch and commit this plan

- [x] Branch `feat/jh-upstream-common`, commit `Add upstream common plan`.

### Task 1: The common module

**Files:**
- Create: `app/core/upstream.py`
- Create: `tests/test_upstream.py`

**Interfaces:**
- Produces: `TIMEOUT_SECONDS = 5`; `new_client() -> httpx2.Client` (timeout 5 s); `upstream_error(source: str, message: str, upstream_code: str | None = None, *, cause: str | None = None) -> AppError` (`AppError("UPSTREAM_ERROR", 502, message, details)`, `details` has `source` and, only when given, `upstream_code`; logs one WARNING on logger `app.upstream` with `source`, `upstream_code`, `cause`); `get(source: str, message: str, url: str, params: dict, *, client: httpx2.Client | None = None) -> httpx2.Response`.

- [x] **Steps 1–5 (done, commit `Add common upstream call handling`):** tests for the params passing, error statuses returned not raised, timeout and connection failure becoming 502 with the given message and `{"source": ...}`, the `upstream_code` detail, a passed client staying open and the default client being closed also on failure, the five-second timeout, failures logged without the key or URL, and `httpx2` request logging staying off; then the module. `tests/test_upstream.py` has 10 tests, all passing.

### Task 2: Docs and verification

**Files:** Modify `docs/dev/팜가디언_아키텍처.md`

- [ ] **Step 1:** Update line 68 (`core/` list) to mention `upstream.py (외부 호출 공통)` and the §8 「공통」 bullet to name `app/core/upstream.py` (`get`, `upstream_error`, `new_client`), say that new external calls (`kma.py`) use it, and say that `farmmap.py` and `vworld.py` implement the same rules themselves. Change nothing else.
- [ ] **Step 2:** `git diff origin/test -- app/farm` → no output (Hyebin's files untouched); `git diff --stat origin/test` lists only the plan, `app/core/upstream.py`, `tests/test_upstream.py` and the architecture document.
- [ ] **Step 3:** `pytest -q -rs` → every test passes, none skipped; `ruff check .` → `All checks passed!`.
- [ ] **Step 4:** Live check of `upstream.get` itself against the real VWorld search URL with the real key from the settings (expect HTTP 200 and JSON; print only status and a boolean), and a call through a transport that raises `ConnectError` with the key in the params (expect 502 `UPSTREAM_ERROR` and a captured log line without the key).
- [ ] **Step 5:** Commit; report: commands and output, that no Hyebin file changed, that `kma.py` can use `upstream.get("kma", ...)`, and that push and PR wait for the user's word.
