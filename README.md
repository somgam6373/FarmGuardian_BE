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
