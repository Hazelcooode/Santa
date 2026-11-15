"""Mobile-only, sign-in-only deployment (MOBILE_ONLY=1, ALLOW_REGISTRATION=0)."""
from app.config import settings


def test_registration_can_be_disabled(app_client, monkeypatch):
    monkeypatch.setattr(settings, "allow_registration", False)
    r = app_client.post("/api/v1/auth/register", json={"email": "new@x.io", "password": "password123", "name": "N"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "REGISTRATION_DISABLED"


def test_mobile_only_sends_root_to_the_app(client, monkeypatch):
    monkeypatch.setattr(settings, "mobile_only", True)
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/mobile/"
    assert client.get("/mobile/").status_code == 200


def test_demo_password_shown_only_when_enabled(app_client, monkeypatch):
    assert settings.test_password not in app_client.get("/login").text
    monkeypatch.setattr(settings, "show_demo_password", True)
    assert settings.test_password in app_client.get("/login").text
