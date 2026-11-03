import csv
import io
import json
import uuid
from datetime import datetime, timezone
from sqlalchemy import select
from fastapi import HTTPException
from openpyxl import load_workbook
from pydantic import ValidationError
from .models import Settings, Customer, Suppression, Audit, Notification, Campaign, Recipient, Message, now
from .schemas import CustomerInput
from .policy import normalize_email, eligible, digest
from .security import email_hash

def locked_settings(db):
    value = db.scalar(select(Settings).where(Settings.id == 1).with_for_update())
    if value is None:
        raise HTTPException(503, "Initialize the database and settings first")
    return value

def audit(db, user, action, target=""):
    db.add(Audit(user_id=user.id if user else None, action=action, target=str(target)))

def notify(db, kind, text):
    db.add(Notification(kind=kind, text=text))

def suppress(db, customer, reason):
    key = email_hash(customer.email)
    if not db.get(Suppression, key):
        db.add(Suppression(email_hash=key, reason=reason))
    customer.subscription_status = reason
    customer.preferences = {**customer.preferences, "marketing": False, "followups": False}
    for message in db.scalars(select(Message).join(Recipient).where(
        Recipient.customer_id == customer.id, Message.state.in_(["queued", "retry"]))):
        message.state = "suppressed"

def add_customer(db, data):
    values = data.model_dump()
    values["email"] = normalize_email(str(data.email))
    if db.get(Suppression, email_hash(values["email"])):
        raise ValueError("Address is permanently suppressed")
    if db.scalar(select(Customer.id).where(Customer.email == values["email"])):
        raise ValueError("Duplicate email address")
    customer = Customer(**values)
    db.add(customer)
    db.flush()
    return customer

def import_contacts(db, content, filename):
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(413, "Maximum import size is 5 MB")
    if filename.lower().endswith(".csv"):
        rows = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    elif filename.lower().endswith(".xlsx"):
        import zipfile
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if sum(x.file_size for x in archive.infolist()) > 25 * 1024 * 1024:
                raise HTTPException(413, "Expanded spreadsheet too large")
        book = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        sheet = book.active
        iterator = sheet.iter_rows(values_only=True)
        header = next(iterator, ())
        if not header or len(set(header)) != len(header):
            raise ValueError("Missing or duplicate column headers")
        rows = (dict(zip(header, row)) for row in iterator)
    else:
        raise HTTPException(415, "Use .csv or .xlsx (legacy .xls is unsupported)")
    count, errors = 0, []
    for number, row in enumerate(rows, start=2):
        if number > 10001:
            raise HTTPException(413, "Maximum 10,000 contacts per import")
        try:
            row = {str(k): v for k, v in row.items() if v is not None and v != ""}
            if isinstance(row.get("preferences"), str):
                row["preferences"] = json.loads(row["preferences"])
            data = CustomerInput.model_validate(row)
            with db.begin_nested():
                add_customer(db, data)
            count += 1
        except (ValueError, ValidationError) as exc:
            errors.append({"row": number, "error": str(exc)[:500]})
    return {"imported": count, "rejected": len(errors), "errors": errors}

def prepare_campaign(db, campaign):
    if campaign.status != "awaiting_approval":
        raise HTTPException(409, "Submit the draft for approval first")
    if campaign.approval_digest:
        raise HTTPException(409, "Campaign already approved")
    customers = select(Customer).where(Customer.subscription_status == "subscribed")
    if campaign.segment:
        customers = customers.where(Customer.segment == campaign.segment)
    total = 0
    for customer in db.scalars(customers):
        if not eligible(customer, db.get(Suppression, email_hash(customer.email)) is not None):
            continue
        recipient = Recipient(campaign_id=campaign.id, customer_id=customer.id)
        db.add(recipient)
        db.flush()
        db.add(Message(id=str(uuid.uuid4()), recipient_id=recipient.id, sequence=0))
        total += 1
    if total == 0:
        raise HTTPException(422, "No eligible opted-in recipients")
    campaign.approval_digest = digest(campaign)
    return total

def csv_document(rows, fields):
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        # Prevent spreadsheet formula execution on exported user-controlled values.
        writer.writerow({k: ("'" + str(v) if str(v).startswith(("=", "+", "-", "@", "\t", "\r")) else v)
                         for k, v in row.items()})
    return stream.getvalue()
