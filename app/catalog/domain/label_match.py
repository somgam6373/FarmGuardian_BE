import re
import unicodedata
from collections.abc import Sequence
from difflib import SequenceMatcher

from app.catalog.domain.entities import LabelCandidate, Pesticide

CUTOFF = 0.5  # 시작값. 실제 포장지 사진으로 맞춘다
MATCH_THRESHOLD = 0.9  # 한 칸이 읽은 값과 맞다고 보는 유사도. CUTOFF처럼 실제 사진으로 맞춘다
MAX_CANDIDATES = 5


def normalize(text: str | None) -> str:
    """NFC·소문자로 바꾸고 글자·숫자가 아닌 것(공백·구두점)을 모두 지운다."""
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFC", text or "").lower())


def _ratio(read: str, catalog: str) -> float:
    # ponytail: 음절 단위 difflib. 한 음절 차이를 놓치거나 띄어쓰기에 약하면
    # 자모 단위(NFD)로 올린다
    return SequenceMatcher(None, read, catalog).ratio()


def _same_company(read: str, catalog: str) -> bool:
    """회사는 「(주)경농」처럼 표기가 갈리므로 한쪽이 다른 쪽을 품어도 같다고 본다."""
    if not read or not catalog:
        return False
    return read in catalog or catalog in read or _ratio(read, catalog) >= MATCH_THRESHOLD


def rank_candidates(
    brand: str | None,
    product: str | None,
    drugs: Sequence[Pesticide],
    *,
    company: str | None = None,
    limit: int = MAX_CANDIDATES,
    cutoff: float = CUTOFF,
) -> list[LabelCandidate]:
    """읽은 상표·품목명과 비슷한 약제를 점수순으로 고른다.

    점수는 읽은 칸의 유사도 평균이다 (품목명만으로는 같은 품목을 쓰는 모든 상표가
    만점이 되므로, 상표와 품목을 함께 읽었으면 평균으로 맞는 상표를 위에 둔다).
    회사는 점수에 넣지 않고, 어느 칸이 맞았는지(`matched`)만 알린다.
    """
    read_brand, read_product = normalize(brand), normalize(product)
    if not read_brand and not read_product:
        return []
    read_company = normalize(company)
    scored = []
    for drug in drugs:
        ratios = {}
        if read_brand:
            ratios["brand"] = _ratio(read_brand, normalize(drug.name))
        if read_product:
            ratios["product"] = _ratio(read_product, normalize(drug.item_name))
        score = sum(ratios.values()) / len(ratios)
        if score >= cutoff:
            matched = [field for field, ratio in ratios.items() if ratio >= MATCH_THRESHOLD]
            if _same_company(read_company, normalize(drug.company)):
                matched.append("company")
            scored.append((score, drug, tuple(matched)))
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
    top = scored[:limit]
    return [LabelCandidate(drug, round(score, 2), matched) for score, drug, matched in top]
