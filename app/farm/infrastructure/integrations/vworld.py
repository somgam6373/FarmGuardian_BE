import json
import logging
from dataclasses import dataclass

import httpx2

from app.core.config import settings
from app.core.errors import AppError

# 요청 URL에 인증키가 들어가므로 httpx2의 요청 로그(INFO)를 끈다
logging.getLogger("httpx2").setLevel(logging.WARNING)

SEARCH_URL = "https://api.vworld.kr/req/search"
TIMEOUT_SECONDS = 5
PAGE_SIZE = 10


@dataclass(frozen=True)
class VworldLot:
    pnu: str
    jibun_addr: str


def _upstream_error(upstream_code: str | None = None) -> AppError:
    details = {"source": "vworld"}
    if upstream_code is not None:
        details["upstream_code"] = upstream_code
    return AppError("UPSTREAM_ERROR", 502, "주소 검색에 실패했습니다", details)


def _parse(text: str) -> tuple[int, list[VworldLot]]:
    # 오류도 HTTP 200으로 오므로 본문의 status로 가른다. 방화벽 거절은 HTML이다
    try:
        response = json.loads(text)["response"]
        status = response["status"]
        if status == "NOT_FOUND":
            return 0, []
        if status == "ERROR":
            raise _upstream_error(response.get("error", {}).get("code"))
        if status != "OK":
            raise _upstream_error()
        lots = [
            VworldLot(pnu=item["id"], jibun_addr=item["address"]["parcel"])
            for item in response["result"]["items"]
        ]
        return int(response["record"]["total"]), lots
    except (ValueError, KeyError, TypeError):
        raise _upstream_error() from None


def search_parcels(
    keyword: str, page: int, *, client: httpx2.Client | None = None
) -> tuple[int, list[VworldLot]]:
    params = {
        "service": "search",
        "request": "search",
        "version": "2.0",
        "type": "address",
        "category": "parcel",
        "crs": "epsg:5179",
        "format": "json",
        "size": PAGE_SIZE,
        "page": page,
        "query": keyword,
        "key": settings.vworld_api_key,
    }
    try:
        if client is None:
            with httpx2.Client(timeout=TIMEOUT_SECONDS) as default_client:
                response = default_client.get(SEARCH_URL, params=params)
        else:
            response = client.get(SEARCH_URL, params=params)
    except httpx2.HTTPError:
        raise _upstream_error() from None
    return _parse(response.text)
