import logging

import httpx2

from app.core.errors import AppError

# 요청 URL에 인증키가 들어가므로 httpx2의 요청 로그(INFO)를 끈다
logging.getLogger("httpx2").setLevel(logging.WARNING)
logger = logging.getLogger("app.upstream")

TIMEOUT_SECONDS = 5


def new_client() -> httpx2.Client:
    return httpx2.Client(timeout=TIMEOUT_SECONDS)


def upstream_error(
    source: str, message: str, upstream_code: str | None = None, *, cause: str | None = None
) -> AppError:
    # 로그에는 출처·코드·원인 이름만 남긴다 (요청 URL과 파라미터에는 인증키가 들어 있다)
    logger.warning(
        "upstream error source=%s upstream_code=%s cause=%s", source, upstream_code, cause
    )
    details = {"source": source}
    if upstream_code is not None:
        details["upstream_code"] = upstream_code
    return AppError("UPSTREAM_ERROR", 502, message, details)


def get(
    source: str, message: str, url: str, params: dict, *, client: httpx2.Client | None = None
) -> httpx2.Response:
    """GET 한 번 (재시도 없음). 연결 실패·타임아웃은 502, HTTP 상태는 호출한 쪽이 판단한다."""
    try:
        if client is None:
            with new_client() as default_client:
                return default_client.get(url, params=params)
        return client.get(url, params=params)
    except httpx2.HTTPError as error:
        # 예외 메시지에 URL이 있을 수 있어 체인을 끊는다
        raise upstream_error(source, message, cause=type(error).__name__) from None
