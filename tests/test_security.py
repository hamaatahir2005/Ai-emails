from datetime import timedelta
import jwt
import pytest
from backend.app.config import config
from backend.app.models import User, now
from backend.app.security import hash_password, verify_password, encrypt, decrypt, token
from backend.app.policy import digest

def test_password_hash_is_salted_and_verifies():
    first = hash_password("long-test-password")
    second = hash_password("long-test-password")
    assert first != second and "long-test-password" not in first
    assert verify_password("long-test-password", first)
    assert not verify_password("wrong-password", first)

def test_backend_secret_encryption():
    value = encrypt("test-provider-api-key")
    assert "test-provider-api-key" not in value
    assert decrypt(value) == "test-provider-api-key"

def test_expired_token_rejected(client):
    value = jwt.encode({"sub": "1", "ver": 0, "exp": now() - timedelta(seconds=1), "iss": "emailos", "aud": "emailos-android"}, config().jwt_secret, algorithm="HS256")
    assert client.get("/customers", headers={"Authorization": "Bearer " + value}).status_code == 401

def test_wrong_audience_rejected(client):
    value = jwt.encode({"sub": "1", "ver": 0, "exp": now() + timedelta(minutes=1), "iss": "emailos", "aud": "other-app"}, config().jwt_secret, algorithm="HS256")
    assert client.get("/customers", headers={"Authorization": "Bearer " + value}).status_code == 401

def test_approval_digest_covers_followups(campaign_data):
    from types import SimpleNamespace
    campaign = SimpleNamespace(**campaign_data)
    original = digest(campaign)
    campaign.followups = [{"delay_days": 3, "subject": "Updated", "body": "Updated content"}]
    assert original != digest(campaign)
