import csv
import io
from sqlalchemy import select
from backend.app.models import Customer, Campaign, Message, Recipient, User, Settings, Event
from backend.app.security import token, unsubscribe_token
from backend.app.policy import digest
from backend.app.services import prepare_campaign

def test_auth_required(client):
    assert client.get("/customers").status_code == 403
    assert client.post("/campaigns/1/approve").status_code == 403

def test_login_and_revocation(client, auth):
    response = client.post("/auth/login", json={"email": "owner@example.com", "password": "test-password-123"})
    assert response.status_code == 200
    session = {"Authorization": "Bearer " + response.json()["access_token"]}
    assert client.get("/auth/me", headers=session).status_code == 200
    assert client.post("/auth/logout", headers=session).status_code == 204
    assert client.get("/auth/me", headers=session).status_code == 401

def test_operator_cannot_approve(client, db):
    auth = {"Authorization": "Bearer " + token(db.get(User, 2))}
    assert client.post("/campaigns/999/approve", headers=auth).status_code == 403

def test_customer_consent_duplicate_and_export(client, auth, contact):
    assert client.post("/customers", headers=auth, json={**contact, "consent_status": False}).status_code == 422
    assert client.post("/customers", headers=auth, json=contact).status_code == 201
    assert client.post("/customers", headers=auth, json={**contact, "email": "CUSTOMER@example.com"}).status_code == 409
    assert "customer@example.com" in client.get("/customers/export", headers=auth).text

def test_csv_import_rejects_unconsented_and_duplicates(client, auth, contact):
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=list(contact))
    writer.writeheader()
    writer.writerow(contact)
    writer.writerow(contact)
    writer.writerow({**contact, "email": "other@example.com", "consent_status": False})
    response = client.post("/customers/import", headers=auth, files={"file": ("contacts.csv", stream.getvalue(), "text/csv")})
    assert response.status_code == 200, response.text
    assert response.json()["imported"] == 1
    assert response.json()["rejected"] == 2

def test_xlsx_import(client, auth, contact):
    from openpyxl import Workbook
    book = Workbook()
    sheet = book.active
    sheet.append(list(contact.keys()))
    sheet.append(list(contact.values()))
    content = io.BytesIO()
    book.save(content)
    result = client.post("/customers/import", headers=auth, files={"file": ("contacts.xlsx", content.getvalue())})
    assert result.status_code == 200
    assert result.json()["imported"] == 1

def prepared(client, auth, contact, campaign_data, db):
    client.post("/customers", headers=auth, json=contact)
    response = client.post("/campaigns", headers=auth, json=campaign_data)
    campaign = db.get(Campaign, response.json()["id"])
    campaign.status = "awaiting_approval"
    prepare_campaign(db, campaign)
    campaign.approved_by = 1
    db.commit()
    return campaign

def test_unapproved_schedule_rejected(client, auth, campaign_data):
    campaign = client.post("/campaigns", headers=auth, json=campaign_data).json()
    response = client.post("/campaigns/" + str(campaign["id"]) + "/schedule", headers=auth, json={"scheduled_at": "2026-12-01T09:00:00Z"})
    assert response.status_code == 409

def test_approval_schedule_and_pause(client, auth, contact, campaign_data, db):
    campaign = prepared(client, auth, contact, campaign_data, db)
    path = "/campaigns/" + str(campaign.id)
    assert client.post(path + "/schedule", headers=auth, json={"scheduled_at": "2026-12-01T09:00:00Z"}).status_code == 200
    assert client.post(path + "/pause", headers=auth).json()["status"] == "paused"
    assert client.post(path + "/resume", headers=auth).status_code == 409 # emergency stop default

def test_unsubscribe_is_permanent_and_get_is_safe(client, auth, contact, campaign_data, db):
    prepared(client, auth, contact, campaign_data, db)
    message = db.scalar(select(Message))
    path = "/unsubscribe/" + message.id + "?token=" + unsubscribe_token(message.id)
    assert client.get(path).status_code == 200
    db.expire_all()
    assert db.scalar(select(Customer)).subscription_status == "subscribed"
    assert client.post(path).status_code == 200
    db.expire_all()
    assert db.scalar(select(Customer)).subscription_status == "unsubscribed"
    assert db.get(Message, message.id).state == "suppressed"
    customer_id = db.scalar(select(Customer.id))
    assert client.delete("/customers/" + str(customer_id), headers=auth).status_code == 204
    assert client.post("/customers", headers=auth, json=contact).status_code == 409

def test_invalid_unsubscribe_token(client):
    assert client.post("/unsubscribe/unknown?token=invalid").status_code == 403

def test_webhook_auth_dedup_and_complaint_stop(client, auth, contact, campaign_data, db):
    campaign = prepared(client, auth, contact, campaign_data, db)
    message = db.scalar(select(Message))
    message.provider_id, message.state = "<provider@example.com>", "accepted"
    campaign.status = "running"
    db.commit()
    body = {"event": "spam", "message-id": message.provider_id, "email": contact["email"]}
    assert client.post("/webhooks/brevo", json=body).status_code == 401
    from backend.app.config import config
    webhook_auth = {"Authorization": "Bearer " + config().webhook_token}
    assert client.post("/webhooks/brevo", headers=webhook_auth, json=body).json()["processed"]
    assert client.post("/webhooks/brevo", headers=webhook_auth, json=body).json()["duplicate"]
    db.expire_all()
    assert db.get(Campaign, campaign.id).status == "paused"
    assert db.scalar(select(Customer)).subscription_status == "complained"
    assert len(list(db.scalars(select(Event)))) == 1

def test_webhook_out_of_order_preserves_delivered_event(client, auth, contact, campaign_data, db):
    prepared(client, auth, contact, campaign_data, db)
    message = db.scalar(select(Message))
    message.provider_id = "<provider@example.com>"
    db.commit()
    from backend.app.config import config
    headers = {"Authorization": "Bearer " + config().webhook_token}
    for kind in ["delivered", "request", "delivered"]:
        assert client.post("/webhooks/brevo", headers=headers, json={"event": kind, "message-id": message.provider_id, "email": contact["email"]}).status_code == 200
    data = client.get("/analytics", headers=auth).json()
    assert data["delivered"] == 1
    assert data["events"]["sent"] == 1
    assert data["replies"] == 0

def test_emergency_stop(client, auth, contact, campaign_data, db):
    campaign = prepared(client, auth, contact, campaign_data, db)
    campaign.status = "running"
    db.commit()
    assert client.post("/settings/emergency-stop", headers=auth).status_code == 204
    db.expire_all()
    assert db.get(Settings, 1).emergency_stop
    assert db.get(Campaign, campaign.id).status == "paused"

def test_analytics_does_not_invent_metrics(client, auth):
    data = client.get("/analytics", headers=auth).json()
    assert data["delivered"] == 0 and data["emails_sent_today"] == 0
    assert data["remaining_daily_capacity"] == 300
    assert "opens" not in data and "clicks" not in data

def test_export_formula_escaping():
    from backend.app.services import csv_document
    assert "'=HYPERLINK" in csv_document([{"name": "=HYPERLINK(x)"}], ["name"])
