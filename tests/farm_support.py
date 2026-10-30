from sqlalchemy import text

from app.core.errors import AppError
from app.farm.infrastructure.integrations import farmmap
from app.farm.infrastructure.integrations.farmmap import FarmmapParcel


def square(farmmap_id: str, x0: float = 0.0, size: float = 10.0) -> FarmmapParcel:
    """x0에서 시작하는 정사각형 필지 (테스트용)."""
    ring = [(x0, 0.0), (x0 + size, 0.0), (x0 + size, size), (x0, size), (x0, 0.0)]
    return FarmmapParcel(farmmap_id, "1" * 19, "1전", "밭", 2022, [[ring]])


def install_fake_farmmap(monkeypatch):
    """id → 정사각형 필지. missing에 있는 id는 None, failing에 있는 id는 502."""
    calls, missing, failing = [], set(), set()

    def fake(farmmap_id, *, client=None):
        calls.append(farmmap_id)
        if farmmap_id in failing:
            raise AppError("UPSTREAM_ERROR", 502, "팜맵 조회에 실패했습니다", {"source": "farmmap"})
        if farmmap_id in missing:
            return None
        return square(farmmap_id, x0=10 * (int(farmmap_id) - 1))

    monkeypatch.setattr(farmmap, "parcel_by_id", fake)
    return calls, missing, failing


def judge(db, zone_id: int, pesticide_id: int, verdict: str = "OK", at: str | None = None) -> int:
    """판정 한 건을 직접 넣는다 (테스트용). at이 없으면 now()."""
    return db.scalar(
        text(
            "INSERT INTO judgment (zone_id, pest_id, pesticide_id, apply_date, verdict, result, "
            "created_at) VALUES (:z, NULL, :drug, '2026-10-29', :v, '{}'::jsonb, "
            "COALESCE(CAST(:at AS timestamptz), now())) RETURNING id"
        ),
        {"z": zone_id, "drug": pesticide_id, "v": verdict, "at": at},
    )
