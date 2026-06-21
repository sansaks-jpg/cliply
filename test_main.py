import urllib.request
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

def test_headers():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"
    print("Tests passed successfully.")

if __name__ == "__main__":
    test_headers()
