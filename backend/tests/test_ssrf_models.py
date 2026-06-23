from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_models_ssrf_protection():
    # Test valid loopback
    res = client.get("/models?base_url=http://127.0.0.1:8000")
    # It might fail with a timeout or connection refused from requests,
    # but it shouldn't return the "Untrusted host" error
    assert res.json().get("error") != "Untrusted host"

    # Test valid localhost
    res = client.get("/models?base_url=http://localhost:1234")
    assert res.json().get("error") != "Untrusted host"

    # Test invalid external host
    res = client.get("/models?base_url=http://example.com")
    assert res.json().get("error") == "Untrusted host"

    # Test invalid IP
    res = client.get("/models?base_url=http://8.8.8.8")
    assert res.json().get("error") == "Untrusted host"

    # Test empty host
    res = client.get("/models?base_url=http://")
    assert res.json().get("error") == "Untrusted host"
