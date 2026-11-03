import hashlib
import hmac
import secrets
import base64
from datetime import timedelta
import jwt
from cryptography.fernet import Fernet
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from .config import config
from .db import database
from .models import User, now

bearer = HTTPBearer()

def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return base64.b64encode(salt + digest).decode()

def verify_password(password, encoded):
    try:
        raw = base64.b64decode(encoded)
        return hmac.compare_digest(raw[16:], hashlib.scrypt(password.encode(), salt=raw[:16], n=16384, r=8, p=1))
    except (ValueError, TypeError):
        return False

def token(user):
    return jwt.encode({"sub": str(user.id), "ver": user.token_version, "exp": now() + timedelta(minutes=config().access_token_minutes), "iss": "emailos", "aud": "emailos-android"}, config().jwt_secret, algorithm="HS256")

def current_user(auth: HTTPAuthorizationCredentials = Depends(bearer), db=Depends(database)):
    try:
        payload = jwt.decode(auth.credentials, config().jwt_secret, algorithms=["HS256"], issuer="emailos", audience="emailos-android", options={"require": ["exp", "sub", "ver"]})
        user = db.get(User, int(payload["sub"]))
        if not user or user.disabled or user.token_version != payload["ver"]:
            raise ValueError()
        return user
    except (jwt.PyJWTError, ValueError, KeyError):
        raise HTTPException(401, "Invalid or expired session")

def admin(user=Depends(current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Administrator required")
    return user

def encrypt(value):
    return Fernet(config().encryption_key.encode()).encrypt(value.encode()).decode()

def decrypt(value):
    return Fernet(config().encryption_key.encode()).decrypt(value.encode()).decode() if value else ""

def email_hash(email):
    return hmac.new(config().unsubscribe_secret.encode(), email.lower().strip().encode(), hashlib.sha256).hexdigest()

def unsubscribe_token(message_id):
    return hmac.new(config().unsubscribe_secret.encode(), ("unsubscribe:" + message_id).encode(), hashlib.sha256).hexdigest()

def check_unsubscribe(message_id, signature):
    return hmac.compare_digest(unsubscribe_token(message_id), signature)
