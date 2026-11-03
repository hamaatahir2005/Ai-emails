import os
from cryptography.fernet import Fernet

# Import-time safety gate: tests never touch a production database.
url = os.environ.get("TEST_DATABASE_URL", "")
if not url or not url.rsplit("/", 1)[-1].startswith("emailos_test"):
    raise RuntimeError("Set TEST_DATABASE_URL to a dedicated PostgreSQL database named emailos_test*")
os.environ["DATABASE_URL"] = url
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-000000000000000000000000")
os.environ.setdefault("UNSUBSCRIBE_SECRET", "test-unsubscribe-000000000000000000000")
os.environ.setdefault("WEBHOOK_TOKEN", "test-webhook-0000000000000000000000000")
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ["SENDING_ENABLED"] = "false"
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")

import pytest
import httpx
from fastapi.testclient import TestClient
from backend.app.db import Base, engine, Session
from backend.app.models import User, Settings
from backend.app.security import hash_password, token
from backend.app.main import app

@pytest.fixture(autouse=True)
def no_real_external_requests(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Real provider HTTP requests are forbidden in tests")
    monkeypatch.setattr(httpx, "request", forbidden)
    monkeypatch.setattr(httpx, "post", forbidden)

@pytest.fixture
def db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session.begin() as session:
        session.add(Settings(id=1, sender_email="sender@example.com", sender_name="Test", postal_address="123 Test Road", dns_confirmed=True))
        session.add(User(email="owner@example.com", password=hash_password("test-password-123"), role="admin"))
        session.add(User(email="operator@example.com", password=hash_password("test-password-123"), role="operator"))
    with Session() as session:
        yield session

@pytest.fixture
def client(db):
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client

@pytest.fixture
def auth(db):
    return {"Authorization": "Bearer " + token(db.get(User, 1))}

@pytest.fixture
def contact():
    return {"full_name": "A Customer", "email": "customer@example.com", "company_name": "Example",
        "business_category": "Retail", "country": "Iraq", "language": "ckb",
        "consent_status": True, "consent_timestamp": "2025-01-01T00:00:00Z",
        "consent_source": "Signup form record consent-123", "segment": "retail"}

@pytest.fixture
def campaign_data():
    return {"name": "Launch", "product_name": "Email OS", "service_description": "Campaign management software",
        "subject": "Hello {{customer_name}}", "body": "Hello {{customer_name}}, {{service_description}}",
        "segment": "retail", "daily_limit": 300, "followups": []}
