from dataclasses import dataclass

from app.catalog.application import catalog_service
from app.catalog.domain.entities import LabelCandidate, LabelRead
from app.catalog.domain.label_match import rank_candidates
from app.catalog.infrastructure.integrations import label_reader


@dataclass(frozen=True)
class LabelScan:
    candidates: list[LabelCandidate]
    read: LabelRead


def scan_label(image: bytes, media_type: str) -> LabelScan:
    """포장지 사진 → 읽은 내용과 후보 약제. 저장하지 않고, 약제는 사용자가 고른다."""
    read = label_reader.read_label(image, media_type)
    drugs = catalog_service.all_pesticides()
    candidates = rank_candidates(read.brand, read.product, drugs, company=read.company)
    return LabelScan(candidates, read)
