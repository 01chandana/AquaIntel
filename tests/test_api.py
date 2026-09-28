import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("AQUAINTEL_SECRET_KEY", "test-secret-key-that-is-long-enough-123456")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_aquaintel.db")

from fastapi.testclient import TestClient

from main import app, FAILED_LOGINS
from database import Base, SessionLocal, engine
from models import User, Asset
from auth import hash_password

Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)
client = TestClient(app)

with SessionLocal() as db:
    db.add(User(email="admin@test.com", password_hash=hash_password("adminpassword123"), role="admin"))
    db.add(Asset(name="Pump Station 1", status="active"))
    db.commit()


def login(email, password):
    response = client.post("/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def test_signup_is_viewer_only_and_case_normalized():
    response = client.post("/signup", json={"email": "Viewer@Example.com", "password": "password123"})
    assert response.status_code == 201
    assert response.json()["role"] == "viewer"
    assert response.json()["email"] == "viewer@example.com"

    # A caller cannot promote itself through a public signup payload.
    response = client.post("/signup", json={"email": "admin2@example.com", "password": "password123", "role": "admin"})
    assert response.status_code == 201
    assert response.json()["role"] == "viewer"


def test_protected_assets_and_session_validation():
    assert client.get("/assets").status_code == 401
    token = login("viewer@example.com", "password123")
    assert client.get("/assets", headers=auth_header(token)).status_code == 200
    assert client.get("/me", headers=auth_header(token)).json()["role"] == "viewer"


def test_viewer_cannot_write():
    token = login("viewer@example.com", "password123")
    assert client.post("/telemetry", headers=auth_header(token), json={"asset_id": 1, "reading_type": "pressure", "value": 1}).status_code == 403
    assert client.post("/alert-rules", headers=auth_header(token), json={"asset_id": 1, "reading_type": "pressure", "max_value": 50}).status_code == 403
    assert client.post("/alerts/1/acknowledge", headers=auth_header(token)).status_code == 403
    assert client.delete("/assets/1", headers=auth_header(token)).status_code == 403


def test_invalid_inputs_return_422_or_404():
    token = login("admin@test.com", "adminpassword123")
    h = auth_header(token)
    assert client.post("/assets", headers=h, json={"name": "Bad", "status": "unknown"}).status_code == 422
    assert client.post("/telemetry", headers=h, json={"asset_id": 99999, "reading_type": "pressure", "value": 1}).status_code == 404
    assert client.get("/assets/1?reading_type=<script>", headers=h).status_code == 422

    response = client.post("/telemetry", headers={**h, "Content-Type": "application/json"}, content='{"asset_id": 1, "reading_type": "pressure", "value": NaN}')
    assert response.status_code == 422
    assert "Telemetry value must be finite" in response.json()["detail"][0]["msg"]


def test_password_length_is_rejected_without_500():
    response = client.post("/signup", json={"email": "long@example.com", "password": "x" * 73})
    assert response.status_code == 422


def test_alert_rules_are_unique_listable_and_deletable():
    token = login("admin@test.com", "adminpassword123")
    h = auth_header(token)
    first = client.post("/alert-rules", headers=h, json={"asset_id": 1, "reading_type": "pressure", "max_value": 50})
    assert first.status_code == 201
    rule_id = first.json()["id"]
    duplicate = client.post("/alert-rules", headers=h, json={"asset_id": 1, "reading_type": "pressure", "max_value": 60})
    assert duplicate.status_code == 409
    assert any(r["id"] == rule_id for r in client.get("/alert-rules", headers=h).json())
    assert client.delete(f"/alert-rules/{rule_id}", headers=h).status_code == 204
    assert client.delete(f"/alert-rules/{rule_id}", headers=h).status_code == 404


def test_alert_trigger_and_acknowledge():
    token = login("admin@test.com", "adminpassword123")
    h = auth_header(token)
    rule = client.post("/alert-rules", headers=h, json={"asset_id": 1, "reading_type": "temperature", "max_value": 50})
    assert rule.status_code == 201
    reading = client.post("/telemetry", headers=h, json={"asset_id": 1, "reading_type": "temperature", "value": 75})
    assert reading.status_code == 201
    alerts = client.get("/alerts?active_only=true", headers=h).json()
    assert alerts and alerts[0]["acknowledged"] is False
    alert_id = alerts[0]["id"]
    ack = client.post(f"/alerts/{alert_id}/acknowledge", headers=h)
    assert ack.status_code == 200
    assert ack.json()["acknowledged"] is True
    assert not any(a["id"] == alert_id for a in client.get("/alerts?active_only=true", headers=h).json())


def test_asset_delete_cascades_related_records():
    token = login("admin@test.com", "adminpassword123")
    h = auth_header(token)
    asset = client.post("/assets", headers=h, json={"name": "QA Cascade Asset", "status": "active"})
    assert asset.status_code == 201
    asset_id = asset.json()["id"]
    assert client.post("/alert-rules", headers=h, json={"asset_id": asset_id, "reading_type": "flow", "max_value": 10}).status_code == 201
    assert client.post("/telemetry", headers=h, json={"asset_id": asset_id, "reading_type": "flow", "value": 20}).status_code == 201
    assert client.delete(f"/assets/{asset_id}", headers=h).status_code == 204
    assert client.get(f"/assets/{asset_id}", headers=h).status_code == 404


def test_prediction_requires_explicit_threshold_and_sensor_scope():
    token = login("admin@test.com", "adminpassword123")
    h = auth_header(token)
    for i in range(4):
        assert client.post("/telemetry", headers=h, json={"asset_id": 1, "reading_type": "flow", "value": 10 + i, "recorded_at": f"2026-09-20T00:0{i}:00Z"}).status_code == 201
    assert client.get("/assets/1/predict?reading_type=flow", headers=h).status_code == 422
    response = client.get("/assets/1/predict?reading_type=flow&threshold=20", headers=h)
    assert response.status_code == 200
    assert response.json()["threshold"] == 20
    assert client.get("/assets/1/anomalies?reading_type=flow", headers=h).status_code == 200


def test_login_rate_limit_and_invalid_credentials():
    FAILED_LOGINS.clear()
    for _ in range(5):
        assert client.post("/login", json={"email": "viewer@example.com", "password": "wrongpassword123"}).status_code == 401
    assert client.post("/login", json={"email": "viewer@example.com", "password": "wrongpassword123"}).status_code == 429
    FAILED_LOGINS.clear()
