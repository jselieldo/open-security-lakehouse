from unittest.mock import patch

import pytest
from app.main import auth_config, live, metrics, ready, system_info
from app.security import require_api_token
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials


def test_liveness_is_public() -> None:
    assert live() == {"status": "ok"}


def test_protected_route_rejects_missing_token() -> None:
    with pytest.raises(HTTPException) as error:
        require_api_token(None)
    assert error.value.status_code == 401


def test_protected_route_accepts_valid_token() -> None:
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer", credentials="test-token-with-at-least-32-characters"
    )
    assert require_api_token(credentials) is None
    assert system_info()["milestone"] == "11"


def test_auth_config_is_public_and_contains_no_secret() -> None:
    config = auth_config()
    assert config.client_id == "osl-console"
    assert config.mode == "hybrid"
    assert "password" not in config.model_dump()


def test_readiness_checks_dependencies() -> None:
    with (
        patch("app.main.check_database"),
        patch("app.main.check_storage"),
    ):
        response = ready()
    assert response["status"] == "ready"
    assert response["object_storage"] == "ok"


def test_readiness_reports_failure_without_leaking_exception() -> None:
    with (
        patch("app.main.check_database", side_effect=RuntimeError("secret details")),
        patch("app.main.check_storage"),
        pytest.raises(HTTPException) as error,
    ):
        ready()
    assert error.value.status_code == 503
    assert "secret details" not in str(error.value.detail)
    assert error.value.detail["failed_dependencies"] == ["database"]


def test_metrics_endpoint_exposes_lake_and_dependency_metrics() -> None:
    with patch("app.main.lake_storage_stats", return_value={"raw": (2, 512)}):
        response = metrics()
    assert b'osl_lake_objects{area="raw"} 2.0' in response.body
    assert b'osl_lake_bytes{area="raw"} 512.0' in response.body
