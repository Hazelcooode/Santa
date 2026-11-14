import os
import sys
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="taimi-test-")
os.environ.update({"TAIMI_DB": os.path.join(_tmp, "test.sqlite3"), "EXA_MODE": "mock", "SCHEDULER": "0",
                   "EXA_API_KEY": "", "GEMINI_API_KEY": "", "CLOUDINARY_URL": "",
                   "DATA_MODE": "demo", "SEED_DEMO_ACCOUNT": "1", "APP_ENV": "development",
                   "ALLOWED_HOSTS": "localhost,127.0.0.1,testserver", "AUTO_PRICE_LOOKUP": "0", "COOKIE_SECURE": "0"})
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import main  # noqa: E402
from app.config import settings  # noqa: E402


@pytest.fixture(scope="session")
def app_client():
    with TestClient(main.app) as c:
        yield c


@pytest.fixture()
def client(app_client):
    app_client.cookies.clear()
    r = app_client.post("/api/v1/auth/login", json={"email": settings.test_email, "password": settings.test_password})
    assert r.status_code == 200, r.text
    return app_client


@pytest.fixture()
def challenge(client):
    def get():
        return {"method": "fingerprint", "challenge": client.get("/api/v1/auth/challenge").json()["challenge"]}
    return get
