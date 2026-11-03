import argparse
import getpass
import secrets
from sqlalchemy import select
from .db import Session
from .models import User, Settings
from .security import hash_password
from .policy import normalize_email

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["create-admin", "create-operator", "create-google-admin", "create-google-operator"])
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    google_only = args.command.startswith("create-google-")
    password = secrets.token_urlsafe(48) if google_only else getpass.getpass("Password (12+ characters): ")
    if len(password) < 12 or len(password) > 128:
        raise SystemExit("Password must have 12–128 characters")
    with Session.begin() as db:
        address = normalize_email(args.email)
        if db.scalar(select(User.id).where(User.email == address)):
            raise SystemExit("User already exists")
        if db.get(Settings, 1) is None:
            db.add(Settings(id=1))
        db.add(User(email=address, password=hash_password(password), role="admin" if args.command in {"create-admin", "create-google-admin"} else "operator"))
    print("Account provisioned. Google-only users sign in with their verified Google identity." if google_only else "Account created; live sending remains disabled by default.")

if __name__ == "__main__":
    main()
