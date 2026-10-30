import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    "rules": ROOT / "app" / "judgment" / "domain" / "rules.py",
    "service": ROOT / "app" / "judgment" / "application" / "service.py",
}
# 판정 규칙 §8: 금지어 검사는 판정 문구(message·notices)에만 적용한다
FORBIDDEN = ["추천", "예측", "예상", "가능성", "위험", "확률", "안전", "문제없"]


def _has_hangul(text: str) -> bool:
    return any("가" <= ch <= "힣" for ch in text)


def korean_literals(source: str) -> list[tuple[int, str]]:
    """독스트링을 뺀 모든 한글 문자열 상수 (f-string의 상수 부분 포함). 주석은 AST에 없다."""
    tree = ast.parse(source)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            first = node.body[0] if node.body else None
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                docstrings.add(id(first.value))
    return [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
        and _has_hangul(node.value)
    ]


def forbidden_in(literals: list[tuple[int, str]]) -> list[tuple[int, str, str]]:
    return [(line, word, text) for line, text in literals for word in FORBIDDEN if word in text]


def _literals(name: str) -> list[tuple[int, str]]:
    return korean_literals(FILES[name].read_text(encoding="utf-8"))


def test_no_template_contains_a_forbidden_word():
    for name in FILES:
        hits = forbidden_in(_literals(name))
        assert not hits, f"{FILES[name].name}: {hits}"


def test_the_scan_sees_the_known_templates():
    rules, service = _literals("rules"), _literals("service")

    assert any("이 병해충에 등록된 약제입니다" in text for _, text in rules)
    assert any("작용기작 미상" in text for _, text in rules)
    assert any("병해충을 지정하면 대안을 볼 수 있습니다" in text for _, text in service)
    assert len(rules) + len(service) > 40  # 지금은 62개. 스캔이 텅 비어 통과하지 않게 한다


def test_the_scanner_flags_a_forbidden_literal():
    hits = forbidden_in(korean_literals("x = '이 약은 안전합니다'"))
    assert [word for _, word, _ in hits] == ["안전"]

    assert forbidden_in(korean_literals('def f():\n    """안전"""\n    return 1')) == []
    assert forbidden_in(korean_literals("# 안전\nx = 1")) == []
    flagged = forbidden_in(korean_literals('n = 1\ny = f"위험 {n}"'))
    assert [word for _, word, _ in flagged] == ["위험"]


@pytest.mark.parametrize("word", FORBIDDEN)
def test_every_forbidden_word_is_detected(word):
    hits = forbidden_in(korean_literals(f"x = '앞 {word} 뒤'"))

    assert [found for _, found, _ in hits] == [word]
