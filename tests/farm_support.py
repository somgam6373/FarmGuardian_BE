from app.farm.infrastructure.integrations.farmmap import FarmmapParcel


def square(farmmap_id: str, x0: float = 0.0, size: float = 10.0) -> FarmmapParcel:
    """x0에서 시작하는 정사각형 필지 (테스트용)."""
    ring = [(x0, 0.0), (x0 + size, 0.0), (x0 + size, size), (x0, size), (x0, 0.0)]
    return FarmmapParcel(farmmap_id, "1" * 19, "1전", "밭", 2022, [[ring]])
