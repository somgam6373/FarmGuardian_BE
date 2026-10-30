# CLAUDE.md

Guidelines for working in FarmGuardian. Bias toward caution over speed; for trivial tasks, use judgment.

Respond to the user in Korean. Write code, identifiers, commits, and docs in English.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

- State assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them. Don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No flexibility or configurability that wasn't requested.
- No error handling for impossible scenarios.
- If 200 lines could be 50, rewrite it.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

- Don't improve adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- Mention unrelated dead code; don't delete it.
- Remove imports/variables/functions that YOUR changes made unused.
- Every changed line must trace directly to the request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

- "Add validation" -> write tests for invalid inputs, then make them pass.
- "Fix the bug" -> write a test that reproduces it, then make it pass.
- "Refactor X" -> tests pass before and after.
- For multi-step tasks, state a brief plan with a check per step:
  `1. [Step] -> verify: [check]`

## Workflow (Superpowers)

The full cycle (think, design, plan, build, verify) is delegated to Superpowers. Use only these four skills. Do not invoke the others.

1. `superpowers:brainstorming`: before adding a feature or changing behavior. A human must approve the design (and the written spec) before moving on. Never skip or assume approval.
2. `superpowers:writing-plans`: after the spec is approved, write the implementation plan.
3. `superpowers:executing-plans`: after the plan is approved, implement it in this session, step by step. Do not use subagent-driven execution.
4. `superpowers:verification-before-completion`: before claiming any work is done, run the tests/lint and confirm the output.

Skip skills 1-3 only for simple bugs and one-line edits, plus questions and read-only exploration. Complex bugs, multi-file changes, and refactors go through the full cycle. Proceed directly under the four principles above.

Design docs, specs, and plans live directly in `docs/dev/` (no subfolders). Check existing files there before writing new ones.

## Backend (this repo root)

- Stack: Python 3.13, FastAPI, SQLAlchemy 2, psycopg 3, pydantic-settings.
- Layout: `app/{core,identity,farm,catalog,judgment,spraying}` (each context split into `domain/application/infrastructure/presentation`, see `docs/dev/팜가디언_아키텍처.md` §4), entrypoint `app/main.py`, schema in `schema.sql`, tests in `tests/`.
- Config comes from env (see `.env.example`). Never commit `.env` or secrets.
- Schema changes go in `schema.sql` only (no Alembic).

Commands:

```
uvicorn app.main:app --reload   # run dev server
pytest                          # run tests
ruff check .                    # lint (line-length 100, rules E/F/I)
psql -d farmguardian -f schema.sql   # create schema on an empty DB (Windows: set PGCLIENTENCODING=UTF8 first)
```

## Frontend

React + Vite.
