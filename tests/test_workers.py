import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from sqlalchemy import select
from backend.app.db import Session
from backend.app.models import Settings, Customer, Campaign, Recipient, Message, DailyUsage, now
from backend.app.policy import digest
from backend.app.services import locked_settings
from workers.tasks import reserve, send_message, dispatch, recover

class FakeRedis:
    hits = 0
    def eval(self, *args):
        type(self).hits += 1
        return type(self).hits
    def set(self, *args, **kwargs):
        return True

def setup_campaign(db, contact, campaign_data, monkeypatch):
    from backend.app.config import config
    cfg = config()
    monkeypatch.setattr(cfg, "sending_enabled", True)
    from datetime import datetime
    values = {**contact, "consent_timestamp": datetime.fromisoformat(contact["consent_timestamp"].replace("Z", "+00:00"))}
    customer = Customer(**values, preferences={})
    campaign = Campaign(**campaign_data, status="running", approved_by=1, approved_at=now())
    db.add_all([customer, campaign])
    db.flush()
    campaign.approval_digest = digest(campaign)
    recipient = Recipient(campaign_id=campaign.id, customer_id=customer.id)
    db.add(recipient)
    db.flush()
    message = Message(id=str(uuid.uuid4()), recipient_id=recipient.id, due_at=now() - timedelta(minutes=1))
    db.add(message)
    settings = db.get(Settings, 1)
    settings.emergency_stop, settings.start_hour, settings.end_hour = False, 0, 24
    db.commit()
    FakeRedis.hits = 0
    monkeypatch.setattr("workers.tasks.Redis.from_url", lambda *a, **kw: FakeRedis())
    return message.id, campaign.id

def test_atomic_daily_capacity_under_concurrency(db):
    settings = db.get(Settings, 1)
    settings.daily_limit = 10
    db.commit()
    def claim(_):
        with Session.begin() as session:
            settings = locked_settings(session)
            return reserve(session, settings, type("Campaign", (), {"id": 1, "daily_limit": 300})(), now())
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(claim, range(40)))
    assert sum(results) == 10

def test_send_task_idempotency(db, contact, campaign_data, monkeypatch):
    message_id, campaign_id = setup_campaign(db, contact, campaign_data, monkeypatch)
    calls = []
    monkeypatch.setattr("workers.tasks.Brevo.send", lambda self, **kwargs: calls.append(kwargs) or "<unique@example.com>")
    send_message.run(message_id)
    send_message.run(message_id)
    db.expire_all()
    assert db.get(Message, message_id).state == "accepted"
    assert len(calls) == 1
    assert "List-Unsubscribe" not in calls[0]["text"] # footer has a usable HTTPS URL
    assert "/unsubscribe/" in calls[0]["text"]
    assert list(db.scalars(select(DailyUsage).where(DailyUsage.campaign_id == 0)))[0].reserved == 1

def test_provider_rate_limited_before_send(db, contact, campaign_data, monkeypatch):
    message_id, _ = setup_campaign(db, contact, campaign_data, monkeypatch)
    FakeRedis.hits = 1000
    send_message.run(message_id)
    db.expire_all()
    assert db.get(Message, message_id).state == "queued"

def test_temporary_rejection_backoff(db, contact, campaign_data, monkeypatch):
    from integrations.brevo import RateLimited
    message_id, _ = setup_campaign(db, contact, campaign_data, monkeypatch)
    def limited(*args, **kwargs):
        raise RateLimited()
    monkeypatch.setattr("workers.tasks.Brevo.send", limited)
    send_message.run(message_id)
    db.expire_all()
    message = db.get(Message, message_id)
    assert message.state == "retry" and message.due_at > now() + timedelta(seconds=60)

def test_uncertain_delivery_never_retried(db, contact, campaign_data, monkeypatch):
    from integrations.brevo import UncertainDelivery
    message_id, campaign_id = setup_campaign(db, contact, campaign_data, monkeypatch)
    calls = []
    def timeout(*args, **kwargs):
        calls.append(1)
        raise UncertainDelivery()
    monkeypatch.setattr("workers.tasks.Brevo.send", timeout)
    send_message.run(message_id)
    send_message.run(message_id)
    db.expire_all()
    assert len(calls) == 1
    assert db.get(Message, message_id).state == "uncertain"
    assert db.get(Campaign, campaign_id).status == "paused"

def test_worker_crash_recovery(db, contact, campaign_data, monkeypatch):
    message_id, campaign_id = setup_campaign(db, contact, campaign_data, monkeypatch)
    message = db.get(Message, message_id)
    message.state, message.sent_at = "sending", now() - timedelta(minutes=10)
    db.commit()
    recover.run()
    db.expire_all()
    assert db.get(Message, message_id).state == "uncertain"
    assert db.get(Campaign, campaign_id).status == "paused"

def test_scheduler_queues_server_side(db, contact, campaign_data, monkeypatch):
    message_id, campaign_id = setup_campaign(db, contact, campaign_data, monkeypatch)
    campaign = db.get(Campaign, campaign_id)
    campaign.status, campaign.scheduled_at = "scheduled", now() - timedelta(minutes=1)
    db.commit()
    queued = []
    monkeypatch.setattr(send_message, "delay", queued.append)
    dispatch.run()
    assert message_id in queued

def test_followup_created_only_after_acceptance(db, contact, campaign_data, monkeypatch):
    campaign_data["followups"] = [{"delay_days": 3, "subject": "Following up", "body": "Approved follow-up"}]
    message_id, _ = setup_campaign(db, contact, campaign_data, monkeypatch)
    monkeypatch.setattr("workers.tasks.Brevo.send", lambda self, **kwargs: "<followup@example.com>")
    send_message.run(message_id)
    db.expire_all()
    followup = db.scalar(select(Message).where(Message.sequence == 1))
    assert followup is not None
    assert followup.due_at > now() + timedelta(days=2)

def test_provider_and_campaign_caps_take_lower_limit(db):
    settings = db.get(Settings, 1)
    settings.daily_limit, settings.provider_daily_limit = 300, 2
    campaign = type("Campaign", (), {"id": 1, "daily_limit": 1})()
    assert reserve(db, settings, campaign, now())
    assert not reserve(db, settings, campaign, now())
    other = type("Campaign", (), {"id": 2, "daily_limit": 300})()
    assert reserve(db, settings, other, now())
    assert not reserve(db, settings, other, now())

def test_unsubscribe_prevents_background_delivery(db, contact, campaign_data, monkeypatch):
    from backend.app.services import suppress
    message_id, _ = setup_campaign(db, contact, campaign_data, monkeypatch)
    suppress(db, db.scalar(select(Customer)), "unsubscribed")
    db.commit()
    calls = []
    monkeypatch.setattr("workers.tasks.Brevo.send", lambda self, **kwargs: calls.append(kwargs))
    send_message.run(message_id)
    assert not calls

def test_reply_stops_queued_followup(db, contact, campaign_data, monkeypatch):
    message_id, _ = setup_campaign(db, contact, campaign_data, monkeypatch)
    message = db.get(Message, message_id)
    recipient = db.get(Recipient, message.recipient_id)
    recipient.replied_at = now()
    db.commit()
    send_message.run(message_id)
    db.expire_all()
    assert db.get(Message, message_id).state == "suppressed"

def test_pause_between_reservation_and_provider_call_keeps_message_for_resume(db, contact, campaign_data, monkeypatch):
    import workers.tasks as tasks
    message_id, campaign_id = setup_campaign(db, contact, campaign_data, monkeypatch)
    original = tasks.deliver_claimed
    def pause_before_call(claimed_id):
        with Session.begin() as session:
            locked_settings(session)
            session.get(Campaign, campaign_id).status = "paused"
        original(claimed_id)
    monkeypatch.setattr(tasks, "deliver_claimed", pause_before_call)
    calls = []
    monkeypatch.setattr("workers.tasks.Brevo.send", lambda self, **kwargs: calls.append(kwargs))
    send_message.run(message_id)
    db.expire_all()
    assert not calls
    assert db.get(Message, message_id).state == "queued"
