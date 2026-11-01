import re
import unicodedata
from collections.abc import Sequence
from difflib import SequenceMatcher

from app.catalog.domain.entities import LabelCandidate, Pesticide

CUTOFF = 0.5  # 시작값. 실제 포장지 사진으로 맞춘다
MAX_CANDIDATES = 5


def normalize(text: str | None) -> str:
    """NFC·소문자로 바꾸고 글자·숫자가 아닌 것(공백·구두점)을 모두 지운다."""
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFC", text or "").lower())


def _ratio(read: str, catalog: str) -> float:
    # ponytail: 음절 단위 difflib. 한 음절 차이를 놓치거나 띄어쓰기에 약하면
    # 자모 단위(NFD)로 올린다
    return SequenceMatcher(None, read, catalog).ratio()


def rank_candidates(
    brand: str | None,
    product: str | None,
    drugs: Sequence[Pesticide],
    *,
    limit: int = MAX_CANDIDATES,
    cutoff: float = CUTOFF,
) -> list[LabelCandidate]:
    """읽은 상표·품목명과 비슷한 약제를 점수순으로 고른다.

    점수는 읽은 칸의 유사도 평균이다 (품목명만으로는 같은 품목을 쓰는 모든 상표가
    만점이 되므로, 상표와 품목을 함께 읽었으면 평균으로 맞는 상표를 위에 둔다).
    """
    read_brand, read_product = normalize(brand), normalize(product)
    if not read_brand and not read_product:
        return []
    scored = []
    for drug in drugs:
        similarities = []
        if read_brand:
            similarities.append(_ratio(read_brand, normalize(drug.name)))
        if read_product:
            similarities.append(_ratio(read_product, normalize(drug.item_name)))
        score = sum(similarities) / len(similarities)
        if score >= cutoff:
            scored.append((score, drug))
    # 같은 점수는 목록 API와 같은 순서: 작용기작(없는 약제 맨 뒤) → 품목명 → 상표명 → id
    scored.sort(
        key=lambda item: (
            -item[0],
            item[1].moa is None,
            item[1].moa.label_kr if item[1].moa else "",
            item[1].item_name,
            item[1].name,
            item[1].id,
        )
    )
    return [LabelCandidate(drug, round(score, 2)) for score, drug in scored[:limit]]
