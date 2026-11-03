import uuid
from datetime import timedelta
from sqlalchemy import select, func
from redis import Redis
from .celery_app import app
from backend.app.db import Session
from backend.app.config import config
from backend.app.models import Settings, Campaign, Customer, Suppression, Recipient, Message, DailyUsage, Event, Notification, Device, User, now
from backend.app.policy import eligible, digest, in_window, render
from backend.app.security import decrypt, email_hash, unsubscribe_token
from backend.app.services import locked_settings, notify
from integrations.brevo import Brevo, RateLimited, CredentialsError, UncertainDelivery, Rejected

def reserve(db, settings, campaign, at):
    day = at.astimezone(__import__("zoneinfo").ZoneInfo(settings.timezone)).date()
    global_usage = db.get(DailyUsage, (day, 0))
    if global_usage is None:
        global_usage = DailyUsage(day=day, campaign_id=0, reserved=0)
        db.add(global_usage)
    usage = db.get(DailyUsage, (day, campaign.id))
    if usage is None:
        usage = DailyUsage(day=day, campaign_id=campaign.id, reserved=0)
        db.add(usage)
    if global_usage.reserved >= min(settings.daily_limit, settings.provider_daily_limit) or usage.reserved >= campaign.daily_limit:
        return False
    global_usage.reserved += 1
    usage.reserved += 1
    return True

@app.task
def dispatch():
    if not config().sending_enabled:
        return
    with Session.begin() as db:
        settings = locked_settings(db)
        if settings.emergency_stop:
            return
        for campaign in db.scalars(select(Campaign).where(Campaign.status == "scheduled", Campaign.scheduled_at <= now())):
            campaign.status = "running"
            notify(db, "started", "Campaign " + str(campaign.id) + " started")
        ids = list(db.scalars(select(Message.id).join(Recipient).join(Campaign).where(
            Campaign.status == "running", Message.state.in_(["queued", "retry"]), Message.due_at <= now()).limit(100)))
    for message_id in ids:
        send_message.delay(message_id)

def pause(db, campaign, reason):
    campaign.status, campaign.pause_reason = "paused", reason
    notify(db, "paused", "Campaign " + str(campaign.id) + ": " + reason)

@app.task
def send_message(message_id):
    # Every mutation affecting sending acquires Settings first, then message.
    # Committed 'sending' state prevents a redelivered Celery task from sending again.
    if not config().sending_enabled:
        return
    with Session.begin() as db:
        settings = locked_settings(db)
        message = db.get(Message, message_id)
        if not message or message.state not in {"queued", "retry"} or message.due_at > now():
            return
        recipient = db.get(Recipient, message.recipient_id)
        campaign = db.get(Campaign, recipient.campaign_id)
        customer = db.get(Customer, recipient.customer_id)
        if settings.emergency_stop or campaign.status != "running" or not in_window(settings, now()):
            return
        if campaign.approval_digest != digest(campaign):
            pause(db, campaign, "Approved content changed")
            return
        if not eligible(customer, db.get(Suppression, email_hash(customer.email)) is not None,
                        bool(recipient.replied_at), message.sequence > 0):
            message.state = "suppressed"
            return
        if message.sequence > 0 and customer.last_email_date and customer.last_email_date > now() - timedelta(days=2):
            message.due_at = customer.last_email_date + timedelta(days=2)
            return
        # Fail closed if Redis is unavailable; Redis counts every outbound attempt.
        redis = Redis.from_url(config().redis_url)
        millis = int(now().timestamp() * 1000)
        script = """redis.call('ZREMRANGEBYSCORE',KEYS[1],'-inf',ARGV[1]-60000)
local count=redis.call('ZCARD',KEYS[1])
if count>=tonumber(ARGV[2]) then return count+1 end
redis.call('ZADD',KEYS[1],ARGV[1],ARGV[3])
redis.call('PEXPIRE',KEYS[1],61000)
return count+1"""
        hits = redis.eval(script, 1, "brevo:rate", millis, settings.provider_per_minute, str(uuid.uuid4()))
        if hits > settings.provider_per_minute:
            return
        if not reserve(db, settings, campaign, now()):
            key = "limit-notice:" + now().date().isoformat() + ":" + str(campaign.id)
            if redis.set(key, "1", nx=True, ex=86400):
                notify(db, "daily_limit", "Daily sending capacity reached")
            return
        message.state = "sending"
        message.attempts += 1
        message.sent_at = now()
    deliver_claimed(message_id)

def deliver_claimed(message_id):
    # Reservation must commit BEFORE network I/O. Recheck eligibility under the
    # same global lock held across the provider call so unsubscribe and stop
    # serialize with outbound requests.
    with Session.begin() as db:
        settings = locked_settings(db)
        message = db.get(Message, message_id)
        if not message or message.state != "sending":
            return
        recipient = db.get(Recipient, message.recipient_id)
        campaign = db.get(Campaign, recipient.campaign_id)
        customer = db.get(Customer, recipient.customer_id)
        if campaign.status == "cancelled":
            message.state = "cancelled"
            return
        if settings.emergency_stop or campaign.status != "running":
            message.state = "queued"
            return
        if not eligible(customer, db.get(Suppression, email_hash(customer.email)) is not None, bool(recipient.replied_at), message.sequence > 0):
            message.state = "suppressed"
            return
        if not in_window(settings, now()):
            message.state = "queued"
            return
        from zoneinfo import ZoneInfo
        zone = ZoneInfo(settings.timezone)
        if message.sent_at.astimezone(zone).date() != now().astimezone(zone).date():
            # The committed reservation belongs to the prior local day.
            # Requeue so a fresh current-day reservation commits before I/O.
            message.state = "queued"
            return
        if campaign.approval_digest != digest(campaign):
            message.state = "uncertain"
            pause(db, campaign, "Approved content changed before dispatch")
            return
        template = {"subject": campaign.subject, "body": campaign.body} if message.sequence == 0 else campaign.followups[message.sequence - 1]
        link = config().public_url + "/unsubscribe/" + message.id + "?token=" + unsubscribe_token(message.id)
        text = render(template["body"], customer, campaign) + "\n\n" + settings.sender_name + "\n" + settings.postal_address + "\nUnsubscribe: " + link
        try:
            message.provider_id = Brevo(decrypt(settings.brevo_key)).send(
                message_id=message.id, to=customer.email, name=customer.full_name,
                sender_email=settings.sender_email, sender_name=settings.sender_name,
                subject=render(template["subject"], customer, campaign), text=text, unsubscribe_url=link)
            message.state = "accepted"
            customer.last_email_date = now()
            db.add(Event(id=uuid.uuid4().hex, message_id=message.id, kind="accepted"))
            if message.sequence < len(campaign.followups):
                next_sequence = message.sequence + 1
                if not db.scalar(select(Message.id).where(Message.recipient_id == recipient.id, Message.sequence == next_sequence)):
                    # Delay is relative to original message; also enforce >=48h gap.
                    delay = campaign.followups[next_sequence - 1]["delay_days"]
                    original = db.scalar(select(Message).where(Message.recipient_id == recipient.id, Message.sequence == 0))
                    due = max(original.sent_at + timedelta(days=delay), now() + timedelta(days=2))
                    db.add(Message(id=str(uuid.uuid4()), recipient_id=recipient.id, sequence=next_sequence, due_at=due))
        except RateLimited:
            message.error = "Provider rate limited the request"
            if message.attempts >= 5:
                message.state = "failed"
                pause(db, campaign, "Repeated provider rate limits")
            else:
                message.state = "retry"
                message.due_at = now() + timedelta(seconds=min(3600, 60 * 2 ** message.attempts))
        except CredentialsError:
            message.state, message.error = "failed", "Provider credentials need attention"
            settings.emergency_stop = True
            for affected in db.scalars(select(Campaign).where(Campaign.status.in_(["running", "scheduled"]))):
                pause(db, affected, message.error)
            notify(db, "credentials", message.error)
        except UncertainDelivery:
            message.state, message.error = "uncertain", "Acceptance unknown; manual provider reconciliation required"
            pause(db, campaign, message.error)
        except Rejected:
            message.state, message.error = "failed", "Provider rejected request"
            pause(db, campaign, message.error)
        if message.error:
            notify(db, "delivery_error", message.error)

@app.task
def recover():
    with Session.begin() as db:
        locked_settings(db)
        for message in db.scalars(select(Message).where(Message.state == "sending", Message.sent_at < now() - timedelta(minutes=5))):
            message.state, message.error = "uncertain", "Worker interrupted; reconcile with provider"
            recipient = db.get(Recipient, message.recipient_id)
            pause(db, db.get(Campaign, recipient.campaign_id), message.error)
        for campaign in db.scalars(select(Campaign).where(Campaign.status == "running")):
            active = db.scalar(select(func.count()).select_from(Message).join(Recipient).where(
                Recipient.campaign_id == campaign.id, Message.state.in_(["queued", "retry", "sending", "uncertain"])))
            if not active:
                campaign.status = "completed"
                notify(db, "completed", "Campaign " + str(campaign.id) + " completed")

@app.task
def push():
    from integrations.notifications import deliver_notifications
    deliver_notifications()

@app.task
def mailbox():
    from integrations.mailbox import poll
    poll()
