"""Use a local RSA signer and certificate transport; never contact Google in tests."""
import hashlib
import json
from datetime import timedelta
from types import SimpleNamespace
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from redis import Redis
from sqlalchemy import select
from backend.app.config import config
from backend.app.models import User, now
from backend.app.security import token

CLIENT_ID = "12345-testclient.apps.googleusercontent.com"

@pytest.fixture(scope="module")
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)

@pytest.fixture
def google(client, monkeypatch, signing_key):
    monkeypatch.setattr(config(), "google_web_client_id", CLIENT_ID)
    public = signing_key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    response = SimpleNamespace(status=200, data=json.dumps({"test-key": public}).encode())
    monkeypatch.setattr("integrations.google_auth.Request", lambda: (lambda *args, **kwargs: response))
    redis = Redis.from_url(config().redis_url)
    redis.delete("google:challenge:testclient", "google:login:testclient")
    def challenge():
        result = client.post("/auth/google/challenge")
        assert result.status_code == 200, result.text
        return result.json()["nonce"]
    def encoded(challenge_nonce, **changes):
        claims = {"sub": "google-owner-123", "email": "owner@example.com", "email_verified": True,
            "hd": "example.com", "iss": "https://accounts.google.com", "aud": CLIENT_ID,
            "iat": int(now().timestamp()), "exp": int((now() + timedelta(minutes=5)).timestamp()), "nonce": challenge_nonce}
        claims.update(changes)
        return jwt.encode(claims, signing_key, algorithm="RS256", headers={"kid": "test-key"})
    def login(nonce=None, **changes):
        nonce = nonce or challenge()
        return client.post("/auth/google", json={"nonce": nonce, "id_token": encoded(nonce, **changes)})
    return SimpleNamespace(challenge=challenge, encoded=encoded, login=login, redis=redis)

def test_google_disabled_without_configuration(client, monkeypatch):
    monkeypatch.setattr(config(), "google_web_client_id", "")
    assert client.post("/auth/google/challenge").status_code == 503

def test_real_signature_login_links_preprovisioned_user(client, db, google):
    response = google.login()
    assert response.status_code == 200, response.text
    assert response.json()["role"] == "admin"
    assert "id_token" not in response.json()
    header = {"Authorization": "Bearer " + response.json()["access_token"]}
    assert client.get("/auth/me", headers=header).json()["id"] == 1
    db.expire_all()
    assert db.get(User, 1).google_sub == "google-owner-123"

@pytest.mark.parametrize("changes", [
    {"email_verified": False}, {"aud": "another-client.apps.googleusercontent.com"},
    {"iss": "https://attacker.example"}, {"nonce": "different-signed-nonce"}, {"nonce": "کوردی-nonce"},
    {"exp": 1000}, {"sub": ""}, {"hd": None}
])
def test_google_rejects_invalid_identity_claims(client, google, changes):
    nonce = google.challenge()
    encoded = google.encoded(nonce, **changes)
    response = client.post("/auth/google", json={"nonce": nonce, "id_token": encoded})
    assert response.status_code == 401, response.text

def test_google_rejects_forged_signature(client, google):
    nonce = google.challenge()
    claims = jwt.decode(google.encoded(nonce), options={"verify_signature": False})
    forged_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    encoded = jwt.encode(claims, forged_key, algorithm="RS256", headers={"kid": "test-key"})
    assert client.post("/auth/google", json={"nonce": nonce, "id_token": encoded}).status_code == 401

def test_nonce_is_single_use(client, google):
    nonce = google.challenge()
    data = {"nonce": nonce, "id_token": google.encoded(nonce)}
    assert client.post("/auth/google", json=data).status_code == 200
    assert client.post("/auth/google", json=data).status_code == 401

def test_expired_challenge_cannot_sign_in(client, google):
    nonce = google.challenge()
    google.redis.delete("google:nonce:" + hashlib.sha256(nonce.encode()).hexdigest())
    assert google.login(nonce).status_code == 401

def test_unknown_google_account_does_not_create_user(db, google):
    assert google.login(email="unapproved@gmail.com").status_code == 403
    db.expire_all()
    assert db.scalar(select(User).where(User.email == "unapproved@gmail.com")) is None

def test_disabled_user_cannot_sign_in(db, google):
    db.get(User, 1).disabled = True
    db.commit()
    assert google.login().status_code == 403

def test_linked_subject_cannot_be_replaced(db, google):
    db.get(User, 1).google_sub = "original-google-subject"
    db.commit()
    assert google.login().status_code == 403
    db.expire_all()
    assert db.get(User, 1).google_sub == "original-google-subject"

def test_google_token_cannot_escalate_local_role(db, google):
    response = google.login(email="operator@example.com", sub="google-operator-123", role="admin")
    assert response.status_code == 200
    assert response.json()["role"] == "operator"

def test_gmail_identity_does_not_require_workspace_domain(db, google):
    db.get(User, 2).email = "approved@gmail.com"
    db.commit()
    assert google.login(email="approved@gmail.com", sub="gmail-approved", hd=None).status_code == 200

def test_google_session_uses_normal_logout_revocation(client, google):
    response = google.login()
    auth = {"Authorization": "Bearer " + response.json()["access_token"]}
    assert client.post("/auth/logout", headers=auth).status_code == 204
    assert client.get("/auth/me", headers=auth).status_code == 401

def test_google_transport_error_fails_closed(client, google, monkeypatch):
    from google.auth.exceptions import TransportError
    def unavailable(*args, **kwargs):
        raise TransportError("Certificate service unavailable")
    monkeypatch.setattr("integrations.google_auth.Request", lambda: unavailable)
    response = google.login()
    assert response.status_code == 503
    assert "access_token" not in response.json()

def test_google_login_rejects_client_supplied_email_and_role(client, google):
    nonce = google.challenge()
    response = client.post("/auth/google", json={"nonce": nonce, "id_token": google.encoded(nonce), "email": "owner@example.com", "role": "admin"})
    assert response.status_code == 422
