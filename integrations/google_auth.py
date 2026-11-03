"""Validate Google-signed ID tokens; never accept client-supplied identity fields."""
import hmac
from google.auth.transport.requests import Request
from google.oauth2 import id_token

class InvalidGoogleIdentity(ValueError):
    pass

def verify_identity(encoded_token, audience, nonce):
    claims = id_token.verify_oauth2_token(encoded_token, Request(), audience=audience)
    # Keep explicit checks even though the SDK also validates issuer and audience.
    if claims.get("iss") not in {"accounts.google.com", "https://accounts.google.com"}:
        raise InvalidGoogleIdentity("Invalid issuer")
    if claims.get("aud") != audience or claims.get("email_verified") is not True:
        raise InvalidGoogleIdentity("Invalid audience or unverified email")
    signed_nonce = claims.get("nonce")
    if not isinstance(signed_nonce, str) or not hmac.compare_digest(signed_nonce.encode("utf-8"), nonce.encode("utf-8")):
        raise InvalidGoogleIdentity("Nonce mismatch")
    subject, address = claims.get("sub"), claims.get("email")
    if not isinstance(subject, str) or not 1 <= len(subject) <= 255 or not isinstance(address, str):
        raise InvalidGoogleIdentity("Missing identity")
    from backend.app.policy import normalize_email
    address = normalize_email(address)
    domain = address.rsplit("@", 1)[1]
    # Google is authoritative for Gmail and hosted Workspace identities. For
    # other externally hosted addresses, old email verification alone is unsafe
    # for automatically linking an existing privileged organization account.
    if domain not in {"gmail.com", "googlemail.com"} and claims.get("hd") != domain:
        raise InvalidGoogleIdentity("Use an authoritative Gmail or Workspace identity")
    return {"subject": subject, "email": address}
