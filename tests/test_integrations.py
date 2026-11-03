import json
import pytest
from integrations.brevo import Brevo, RateLimited, UncertainDelivery
from integrations.gemini import generate

def test_gemini_request_and_output(monkeypatch):
    requests = []
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": json.dumps({"subject": "Hello", "body": "Approved facts only"})}]}}]}
    def post(url, **kwargs):
        requests.append((url, kwargs))
        return Response()
    monkeypatch.setattr("httpx.post", post)
    result = generate("test-key", "gemini-test", business={"product_name": "Example"},
                      customer={}, instruction="Introduction", language="ckb")
    assert result["subject"] == "Hello"
    assert requests[0][1]["headers"]["x-goog-api-key"] == "test-key"
    assert "Never invent" in requests[0][1]["json"]["systemInstruction"]["parts"][0]["text"]

def test_brevo_payload_unsubscribe_and_idempotency(monkeypatch):
    requests = []
    class Response:
        status_code = 201
        is_error = False
        def json(self): return {"messageId": "<id@example.com>"}
    def request(*args, **kwargs):
        requests.append(kwargs)
        return Response()
    monkeypatch.setattr("httpx.request", request)
    Brevo("test-key").send(message_id="stable-id", to="test@example.com", name="Test",
        sender_email="sender@example.com", sender_name="Sender", subject="Test", text="Body",
        unsubscribe_url="https://example.com/unsubscribe/id?token=token")
    headers = requests[0]["json"]["headers"]
    assert headers["idempotencyKey"] == "stable-id"
    assert headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"

@pytest.mark.parametrize("status,error", [(429, RateLimited), (503, UncertainDelivery)])
def test_brevo_failure_classification(monkeypatch, status, error):
    class Response:
        status_code = status
        is_error = True
    monkeypatch.setattr("httpx.request", lambda *a, **kw: Response())
    with pytest.raises(error):
        Brevo("test-key").request("GET", "/senders")

def test_authorized_mailbox_reply_stops_followups(db, monkeypatch, contact, campaign_data):
    import uuid
    from datetime import datetime
    from sqlalchemy import select
    from backend.app.config import config
    from backend.app.models import Customer, Campaign, Recipient, Message, Counter, now
    from integrations.mailbox import poll
    cfg = config()
    monkeypatch.setattr(cfg, "mailbox_host", "imap.example.com")
    monkeypatch.setattr(cfg, "mailbox_user", "sender@example.com")
    monkeypatch.setattr(cfg, "mailbox_password", "test-only-password")
    values = {**contact, "consent_timestamp": datetime.fromisoformat(contact["consent_timestamp"].replace("Z", "+00:00"))}
    customer = Customer(**values, preferences={})
    campaign = Campaign(**campaign_data)
    db.add_all([customer, campaign])
    db.flush()
    recipient = Recipient(campaign_id=campaign.id, customer_id=customer.id)
    db.add(recipient)
    db.flush()
    original = Message(id=str(uuid.uuid4()), recipient_id=recipient.id, sequence=0, state="accepted", provider_id="<original@example.com>")
    queued = Message(id=str(uuid.uuid4()), recipient_id=recipient.id, sequence=1, state="queued")
    db.add_all([original, queued])
    db.commit()
    class Mailbox:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def login(self, *args): return "OK", []
        def select(self, *args, **kwargs): return "OK", []
        def response(self, key): return key, [b"123" if key == "UIDVALIDITY" else b"101"]
        def uid(self, command, *args):
            if command == "search": return "OK", [b"101"]
            return "OK", [(b"header", b"From: customer@example.com\r\nIn-Reply-To: <original@example.com>\r\n\r\n")]
    monkeypatch.setattr("imaplib.IMAP4_SSL", Mailbox)
    poll() # Initializes cursor, skips historical mail.
    db.expire_all()
    assert db.get(Recipient, recipient.id).replied_at is None
    poll()
    db.expire_all()
    assert db.get(Recipient, recipient.id).replied_at is not None
    assert db.get(Message, queued.id).state == "suppressed"

def test_notification_outbox_without_devices_stays_pending(db, monkeypatch):
    import firebase_admin
    from backend.app.models import Notification
    from integrations.notifications import deliver_notifications
    monkeypatch.setattr(firebase_admin, "initialize_app", lambda **kwargs: None)
    notice = Notification(kind="started", text="Campaign started")
    db.add(notice)
    db.commit()
    deliver_notifications()
    db.expire_all()
    assert db.get(Notification, notice.id).delivered is False

def test_notification_delivery_records_actual_success(db, monkeypatch):
    import firebase_admin
    from firebase_admin import messaging
    from backend.app.models import Notification, Device
    from integrations.notifications import deliver_notifications
    monkeypatch.setattr(firebase_admin, "initialize_app", lambda **kwargs: None)
    calls = []
    monkeypatch.setattr(messaging, "send", lambda message: calls.append(message) or "test-message-id")
    notice = Notification(kind="completed", text="Campaign completed")
    db.add_all([notice, Device(token="test-device-token", user_id=1)])
    db.commit()
    deliver_notifications()
    db.expire_all()
    assert db.get(Notification, notice.id).delivered
    assert len(calls) == 1
