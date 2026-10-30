# FarmGuardian_BE

## 브랜치 전략

```
main   시연·제출 기준. 항상 실행되는 상태
 └─ test   통합 브랜치. 기능을 여기에 모아 확인한다
     └─ feat/<이니셜>-<주제>   기능 작업 (예: feat/hb-parcels)
```

- 기능 작업은 `test`에서 `feat/...` 브랜치를 따서 하고, 끝나면 `test`로 PR을 만든다. 상대가 한 번 보고 머지한다.
- `test`에서 `pytest`와 `ruff check .`가 통과하면 `main`으로 머지한다.
- 버그 수정은 `fix/...`로 같은 방식으로 한다.
- `main`, `test`에는 직접 푸시하지 않는다.

## 실행

필요한 것: Python 3.13, PostgreSQL 17 + PostGIS (로컬에 직접 설치한다. docker는 쓰지 않는다)

```
python -m venv .venv
.venv\Scripts\activate              # macOS·Linux는 source .venv/bin/activate
pip install -r requirements-dev.txt
copy .env.example .env              # macOS·Linux는 cp. 아래 값을 채운다
```

`.env` 값
- `DATABASE_URL`, `TEST_DATABASE_URL`: 개발 DB와 테스트 DB. 테스트 DB 이름은 `_test`로 끝나야 한다 (없으면 DB 테스트는 skip된다).
- `CORS_ORIGINS`: 프론트 주소. 쉼표로 여러 개 (기본 `http://localhost:3000`).
- `FARMMAP_API_KEY`(공공데이터포털 팜맵), `VWORLD_API_KEY`(브이월드): 인증키. 커밋하지 않는다.

DB 만들기 (두 DB 모두, 빈 DB에서 한 번)

```
psql -d farmguardian -f schema.sql
psql -d farmguardian_test -f schema.sql
python -m app.seed_demo --dev-user    # 개발용 사용자 dev (id 1). 프론트가 X-User-Id로 쓴다
```

- DB는 먼저 만들어 둔다 (`createdb` 또는 DB 도구). 한글 Windows는 `psql` 전에 `set PGCLIENTENCODING=UTF8`을 한다.
- `schema.sql`을 바꾸면 마이그레이션 도구가 없으므로 테이블을 지우고 다시 적용한다.

서버·테스트·린트

```
uvicorn app.main:app --reload     # http://localhost:8000 (API 문서는 /docs)
pytest                            # 실제 PostGIS 테스트 DB가 필요하다
ruff check .
```

## API 테스트 페이지

지금 구현된 API를 브라우저에서 눌러 보는 개발용 페이지다. 서버가 `/openapi.json`으로 알려 주는 구현 여부를 보고, 아직 없는 API는 「아직 구현 안 됨」으로 표시한다.

```
uvicorn app.main:app --reload     # API (8000)
cd docs\dev
python -m http.server 3000        # 페이지 (CORS가 3000을 허용한다)
```

`http://localhost:3000/api_playground.html`을 연다. `file://`로 열면 CORS 때문에 호출되지 않는다.

## 문서

`docs/dev/`에 있다.
- `팜가디언_API_명세.md`: 프론트와 맺는 API 계약. 바뀌면 안 된다.
- `팜가디언_아키텍처.md`, `팜가디언_판정_규칙.md`, `팜가디언_역할분담_일정.md`, `팜가디언_PRD_수정_제안.md`
- `날짜-주제-design.md`, `날짜-주제-plan.md`: 기능별 설계와 구현 계획
- `farmguardian_backlog_BE.xlsx`, `farmguardian_backlog_FE.xlsx`: 작업 백로그
