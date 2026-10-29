import functools
import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
_NAMES = frozenset(
    {
        "crop",
        "moa",
        "ingredient",
        "pest",
        "pest_alias",
        "pest_photo",
        "pest_season",
        "pesticide_use",
        "safe_use_std",
        "use_ingredient",
        "rotation_rule",
        "virus_vector",
    }
)


@functools.cache
def load(name: str) -> list[dict]:
    # 결과는 모든 호출이 공유한다. 수정하지 않는다.
    if name not in _NAMES:
        raise ValueError(f"unknown catalog file: {name!r}")
    return json.loads((DATA_DIR / f"{name}.json").read_text(encoding="utf-8"))
