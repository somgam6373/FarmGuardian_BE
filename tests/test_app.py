from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.errors import AppError
from app.main import app


# 테스트 전용 라우트: 프로덕션 코드에 에러를 내는 경로를 두지 않기 위해 여기서만 등록한다.
@app.get("/_test/int/{n}")
def _int(n: int):
    return n


@app.get("/_test/app-error")
def _app_error():
    raise AppError("PARCEL_ALREADY_USED", 409, "이미 사용 중인 필지", {"farmmap_ids": [1]})


@app.get("/_test/unauthorized")
def _unauthorized():
    raise HTTPException(401, "토큰 없음", headers={"WWW-Authenticate": "Bearer"})


client = TestClient(app)


def test_health_returns_ok():
    r = client.get("/health")

    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_unknown_path_returns_not_found_error_body():
    r = client.get("/nope")

    assert r.status_code == 404
    assert r.json() == {"error": {"code": "NOT_FOUND", "message": "Not Found"}}


def test_unauthorized_keeps_www_authenticate_header():
    r = client.get("/_test/unauthorized")

    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"
    assert r.headers["www-authenticate"] == "Bearer"


def test_other_http_errors_use_generic_code():
    r = client.post("/health")

    assert r.status_code == 405
    assert r.json()["error"]["code"] == "HTTP_ERROR"


def test_invalid_param_returns_validation_error_body():
    r = client.get("/_test/int/abc")

    assert r.status_code == 422
    error = r.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"]["errors"][0]["loc"] == ["path", "n"]


def test_validation_error_does_not_echo_input():
    r = client.get("/_test/int/secret-value")

    assert "secret-value" not in r.text


def test_app_error_returns_its_code_status_and_details():
    r = client.get("/_test/app-error")

    assert r.status_code == 409
    assert r.json() == {
        "error": {
            "code": "PARCEL_ALREADY_USED",
            "message": "이미 사용 중인 필지",
            "details": {"farmmap_ids": [1]},
        }
    }


def test_cors_allows_configured_origin():
    origin = settings.cors_origins.split(",")[0]

    r = client.get("/health", headers={"Origin": origin})

    assert r.headers["access-control-allow-origin"] == origin


def test_cors_does_not_allow_unlisted_origin():
    r = client.get("/health", headers={"Origin": "http://evil.example"})

    assert "access-control-allow-origin" not in r.headers
