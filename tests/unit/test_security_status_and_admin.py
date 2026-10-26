"""Unit tests verifying status API sanitization and admin endpoint authorization."""

import pytest
from starlette.testclient import TestClient
from graph_intelligence.remote.server import app, ADMIN_SECRET_KEY
import graph_intelligence.remote.server as server_module


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


def test_status_api_structure_and_no_leakage(client):
    """Verify that /api/status returns only high-level status and never server details."""
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()

    # 1. Structure must strictly only have 'status' and 'services'
    assert set(data.keys()) == {"status", "services"}
    assert data["status"] in ("healthy", "degraded")
    assert set(data["services"].keys()) == {"auth_database", "graph_store"}
    assert data["services"]["auth_database"] in ("healthy", "unavailable")
    assert data["services"]["graph_store"] in ("healthy", "unavailable")

    # 2. Strict verification: NO server details or sensitive keys allowed
    forbidden_keys = {
        "host", "port", "database", "falkordb", "target", "engine",
        "error", "use_postgres", "guest_count", "node_count", "ssl",
        "graph", "connection", "password", "username", "sqlite_path"
    }
    assert not (forbidden_keys & set(data.keys())), f"Found forbidden top-level keys: {forbidden_keys & set(data.keys())}"

    # 3. Check for any path, host, or stack trace leaks in text serialization
    raw_text = response.text.lower()
    for leak in ["c:\\", "/home/", "/opt/", "6379", "5432", "traceback", "exception"]:
        assert leak not in raw_text, f"Potential information disclosure: found '{leak}' in /api/status response"


def test_admin_cleanup_forbidden_when_key_unset(client, monkeypatch):
    """When ADMIN_SECRET_KEY is empty, admin cleanup must be completely disabled (403)."""
    monkeypatch.setattr(server_module, "ADMIN_SECRET_KEY", "")
    res = client.post("/api/admin/cleanup?days=2")
    assert res.status_code == 403
    assert res.json()["error"] == "forbidden"


def test_admin_cleanup_unauthorized_with_missing_or_invalid_key(client, monkeypatch):
    """When ADMIN_SECRET_KEY is configured, unauthenticated or bad-token calls must be rejected (401)."""
    monkeypatch.setattr(server_module, "ADMIN_SECRET_KEY", "super-secret-admin-key")

    # No auth header
    res1 = client.post("/api/admin/cleanup?days=2")
    assert res1.status_code == 401
    assert res1.json()["error"] == "unauthorized"

    # Wrong Bearer token
    res2 = client.post("/api/admin/cleanup?days=2", headers={"Authorization": "Bearer wrong-key"})
    assert res2.status_code == 401
    assert res2.json()["error"] == "unauthorized"

    # Wrong X-Admin-Key
    res3 = client.post("/api/admin/cleanup?days=2", headers={"X-Admin-Key": "wrong-key"})
    assert res3.status_code == 401
    assert res3.json()["error"] == "unauthorized"


def test_admin_cleanup_bounds_validation(client, monkeypatch):
    """Verify that days parameter must be >= 1."""
    monkeypatch.setattr(server_module, "ADMIN_SECRET_KEY", "super-secret-admin-key")
    headers = {"Authorization": "Bearer super-secret-admin-key"}

    # days = 0 must be rejected
    res_zero = client.post("/api/admin/cleanup?days=0", headers=headers)
    assert res_zero.status_code == 400
    assert res_zero.json()["error"] == "bad_request"

    # days = -5 must be rejected
    res_neg = client.post("/api/admin/cleanup?days=-5", headers=headers)
    assert res_neg.status_code == 400
    assert res_neg.json()["error"] == "bad_request"


def test_admin_cleanup_authorized(client, monkeypatch):
    """Authorized cleanup must succeed and return high-level operation metrics."""
    monkeypatch.setattr(server_module, "ADMIN_SECRET_KEY", "super-secret-admin-key")
    headers = {"Authorization": "Bearer super-secret-admin-key"}

    res = client.post("/api/admin/cleanup?days=2", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert "deleted_guest_count" in data
    assert "deleted_session_logs_count" in data
    assert "falkordb_cleaned_nodes" in data


def test_unhandled_exception_handler_sanitization():
    """Ensure any unhandled server exception returns a generic 500 error without leaking stack traces."""
    from starlette.routing import Route

    async def faulty_route(request):
        raise RuntimeError("Sensitive internal database connection failed at line 42")

    # Insert before catch-all mount
    app.router.routes.insert(0, Route("/api/test-fault-simulation", faulty_route, methods=["GET"]))

    test_client = TestClient(app, raise_server_exceptions=False)
    res = test_client.get("/api/test-fault-simulation")
    assert res.status_code == 500
    data = res.json()
    assert data == {"error": "internal_error", "message": "An internal server error occurred."}
    assert "Sensitive internal database connection failed" not in res.text
    assert "Traceback" not in res.text
