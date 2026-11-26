from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint_returns_service_status() -> None:
    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "MetaAnalyzer"}


def test_authentication_and_investigation_routers_are_registered() -> None:
    routes = {(method, route.path) for route in app.routes for method in getattr(route, "methods", [])}

    assert ("POST", "/api/auth/register") in routes
    assert ("POST", "/api/auth/login") in routes
    assert ("POST", "/api/auth/refresh") in routes
    assert ("POST", "/api/auth/logout") in routes
    assert ("POST", "/api/investigations") in routes
    assert ("GET", "/api/investigations/{investigation_id}") in routes
