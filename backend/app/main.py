import hashlib
import hmac
import json
from datetime import timedelta
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Header, Request
from fastapi.responses import Response, HTMLResponse
from sqlalchemy import select, func, delete
from sqlalchemy.exc import IntegrityError
from redis import Redis
from .config import config
from .db import database
from .models import User, Settings, Customer, Campaign, Recipient, Message, Suppression, Event, DailyUsage, Device, Counter, Audit, now
from .schemas import Login, CustomerInput, CampaignInput, Schedule, SettingsInput, Generate, Preview, DeviceInput, PasswordChange, Preferences, Reconcile
from .security import current_user, admin, token, verify_password, hash_password, encrypt, decrypt, email_hash, check_unsubscribe
from .policy import normalize_email, render, digest
from .services import locked_settings, audit, notify, suppress, add_customer, import_contacts, prepare_campaign, csv_document

app = FastAPI(title="AI Email Marketing OS", version="1.0.0",
    description="Single-organization permission-based marketing. Live sending is disabled by default.")

@app.middleware("http")
async def secure_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'none'; form-action 'self'; frame-ancestors 'none'"
    return response

@app.exception_handler(IntegrityError)
async def conflict(request, exc):
    return __import__("fastapi").responses.JSONResponse(status_code=409, content={"detail": "Duplicate or conflicting record"})

def view(model, exclude=()):
    return {c.name: getattr(model, c.name) for c in model.__table__.columns if c.name not in exclude}

def get_campaign(db, campaign_id):
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(404, "Campaign not found")
    return campaign

def get_customer(db, customer_id):
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(404, "Customer not found")
    return customer

def rate_limit(key, limit, period):
    redis = Redis.from_url(config().redis_url)
    try:
        hits = redis.eval("local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],ARGV[1]) end; return n", 1, key, period)
    except Exception:
        raise HTTPException(503, "Rate limiting service unavailable")
    if hits > limit:
        raise HTTPException(429, "Too many requests")

@app.get("/health")
def health(db=Depends(database)):
    db.execute(select(Settings.id).limit(1))
    Redis.from_url(config().redis_url).ping()
    return {"status": "ok"}

@app.post("/auth/login")
def login(data: Login, request: Request, db=Depends(database)):
    # Configure trusted reverse proxy IPs in uvicorn; never trust arbitrary X-Forwarded-For.
    address = request.client.host if request.client else "unknown"
    rate_limit("login:ip:" + address, 20, 300)
    rate_limit("login:account:" + hashlib.sha256(str(data.email).lower().encode()).hexdigest(), 10, 300)
    user = db.scalar(select(User).where(User.email == str(data.email).lower()))
    # Perform password work for nonexistent accounts too.
    valid = verify_password(data.password, user.password if user else hash_password("nonexistent-account"))
    if not user or not valid or user.disabled:
        raise HTTPException(401, "Invalid credentials")
    audit(db, user, "login")
    db.commit()
    return {"access_token": token(user), "token_type": "bearer", "expires_in": config().access_token_minutes * 60, "role": user.role}

@app.get("/auth/me")
def me(user=Depends(current_user)):
    return view(user, ("password",))

@app.post("/auth/logout", status_code=204)
def logout(user=Depends(current_user), db=Depends(database)):
    user.token_version += 1
    db.execute(delete(Device).where(Device.user_id == user.id))
    audit(db, user, "logout")
    db.commit()

@app.post("/auth/password", status_code=204)
def password(data: PasswordChange, user=Depends(current_user), db=Depends(database)):
    if not verify_password(data.old_password, user.password):
        raise HTTPException(403, "Incorrect current password")
    user.password = hash_password(data.new_password)
    user.token_version += 1
    audit(db, user, "password_changed")
    db.commit()

@app.get("/customers")
def customers(q: str = "", category: str = "", segment: str = "", offset: int = 0, limit: int = 100, user=Depends(current_user), db=Depends(database)):
    if offset < 0 or not 1 <= limit <= 200 or len(q) > 200:
        raise HTTPException(422, "Invalid pagination or query")
    query = select(Customer)
    if q:
        query = query.where(Customer.full_name.icontains(q, autoescape=True) | Customer.email.icontains(q, autoescape=True))
    if category:
        query = query.where(Customer.business_category == category)
    if segment:
        query = query.where(Customer.segment == segment)
    return [view(row) for row in db.scalars(query.order_by(Customer.id).offset(offset).limit(limit))]

@app.post("/customers", status_code=201)
def create_customer(data: CustomerInput, user=Depends(current_user), db=Depends(database)):
    locked_settings(db)
    try:
        customer = add_customer(db, data)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    audit(db, user, "customer_created", customer.id)
    db.commit()
    return view(customer)

@app.post("/customers/import")
async def customer_import(file: UploadFile = File(...), user=Depends(current_user), db=Depends(database)):
    locked_settings(db)
    content = await file.read(5 * 1024 * 1024 + 1)
    try:
        result = import_contacts(db, content, file.filename or "")
    except (ValueError, UnicodeError, __import__("zipfile").BadZipFile) as exc:
        raise HTTPException(422, "Invalid import file: " + str(exc)[:200])
    audit(db, user, "customers_imported", result["imported"])
    db.commit()
    return result

@app.get("/customers/export")
def customer_export(user=Depends(admin), db=Depends(database)):
    fields = [c.name for c in Customer.__table__.columns]
    rows = [view(c) for c in db.scalars(select(Customer).order_by(Customer.id))]
    audit(db, user, "customers_exported")
    db.commit()
    return Response(csv_document(rows, fields), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="customers.csv"'})

@app.get("/customers/{customer_id}")
def customer_details(customer_id: int, user=Depends(current_user), db=Depends(database)):
    customer = get_customer(db, customer_id)
    history = [view(m) for m in db.scalars(select(Message).join(Recipient).where(Recipient.customer_id == customer_id))]
    return {"customer": view(customer), "history": history}

@app.put("/customers/{customer_id}/preferences")
def preferences(customer_id: int, data: Preferences, user=Depends(current_user), db=Depends(database)):
    locked_settings(db)
    customer = get_customer(db, customer_id)
    customer.preferences = {"marketing": data.marketing, "followups": data.followups}
    customer.segment = data.segment
    if not data.marketing:
        suppress(db, customer, "unsubscribed")
    audit(db, user, "customer_preferences", customer_id)
    db.commit()
    return view(customer)

@app.post("/customers/{customer_id}/suppress", status_code=204)
def suppress_customer(customer_id: int, user=Depends(current_user), db=Depends(database)):
    locked_settings(db)
    suppress(db, get_customer(db, customer_id), "suppressed")
    audit(db, user, "customer_suppressed", customer_id)
    db.commit()

@app.delete("/customers/{customer_id}", status_code=204)
def delete_customer(customer_id: int, user=Depends(admin), db=Depends(database)):
    locked_settings(db)
    customer = get_customer(db, customer_id)
    suppress(db, customer, "deleted")
    db.flush()
    db.delete(customer)
    audit(db, user, "customer_deleted", customer_id)
    db.commit()

@app.get("/segments")
def segments(user=Depends(current_user), db=Depends(database)):
    return list(db.scalars(select(Customer.segment).distinct().order_by(Customer.segment)))

@app.get("/suppressions")
def suppressions(user=Depends(admin), db=Depends(database)):
    return [view(s) for s in db.scalars(select(Suppression).order_by(Suppression.created_at.desc()).limit(500))]

@app.get("/campaigns")
def campaigns(user=Depends(current_user), db=Depends(database)):
    return [view(c) for c in db.scalars(select(Campaign).order_by(Campaign.id.desc()).limit(500))]

@app.post("/campaigns", status_code=201)
def create_campaign(data: CampaignInput, user=Depends(current_user), db=Depends(database)):
    campaign = Campaign(**data.model_dump())
    db.add(campaign)
    db.flush()
    audit(db, user, "campaign_created", campaign.id)
    db.commit()
    return view(campaign)

@app.put("/campaigns/{campaign_id}")
def edit_campaign(campaign_id: int, data: CampaignInput, user=Depends(current_user), db=Depends(database)):
    locked_settings(db)
    campaign = get_campaign(db, campaign_id)
    if campaign.status != "draft":
        raise HTTPException(409, "Only drafts can be edited; create a new draft for approved content")
    for key, value in data.model_dump().items():
        setattr(campaign, key, value)
    audit(db, user, "campaign_edited", campaign_id)
    db.commit()
    return view(campaign)

@app.post("/campaigns/{campaign_id}/submit")
def submit_campaign(campaign_id: int, user=Depends(current_user), db=Depends(database)):
    locked_settings(db)
    campaign = get_campaign(db, campaign_id)
    if campaign.status != "draft":
        raise HTTPException(409, "Campaign is not a draft")
    campaign.status = "awaiting_approval"
    audit(db, user, "campaign_submitted", campaign_id)
    db.commit()
    return view(campaign)

@app.post("/campaigns/{campaign_id}/approve")
def approve_campaign(campaign_id: int, user=Depends(admin), db=Depends(database)):
    settings = locked_settings(db)
    if not settings.dns_confirmed or not settings.postal_address or not settings.brevo_key:
        raise HTTPException(422, "Configure verified sender, postal address, SPF, DKIM and DMARC first")
    from integrations.brevo import Brevo
    try:
        verified = Brevo(decrypt(settings.brevo_key)).verify_sender(settings.sender_email)
    except Exception:
        raise HTTPException(502, "Unable to verify Brevo sender")
    if not verified:
        raise HTTPException(422, "Sender is not active in Brevo")
    campaign = get_campaign(db, campaign_id)
    total = prepare_campaign(db, campaign)
    campaign.approved_by, campaign.approved_at = user.id, now()
    audit(db, user, "campaign_approved", campaign_id)
    db.commit()
    return {"campaign": view(campaign), "total_recipients": total}

@app.post("/campaigns/{campaign_id}/schedule")
def schedule_campaign(campaign_id: int, data: Schedule, user=Depends(admin), db=Depends(database)):
    locked_settings(db)
    campaign = get_campaign(db, campaign_id)
    if campaign.status != "awaiting_approval" or not campaign.approved_by or campaign.approval_digest != digest(campaign):
        raise HTTPException(409, "Explicit approval of current content is required")
    campaign.scheduled_at, campaign.status = data.scheduled_at, "scheduled"
    audit(db, user, "campaign_scheduled", campaign_id)
    db.commit()
    return view(campaign)

@app.post("/campaigns/{campaign_id}/pause")
def pause_campaign(campaign_id: int, user=Depends(current_user), db=Depends(database)):
    locked_settings(db)
    campaign = get_campaign(db, campaign_id)
    if campaign.status not in {"running", "scheduled"}:
        raise HTTPException(409, "Campaign cannot be paused")
    campaign.status, campaign.pause_reason = "paused", "Paused by operator"
    notify(db, "paused", "Campaign " + str(campaign_id) + " paused")
    audit(db, user, "campaign_paused", campaign_id)
    db.commit()
    return view(campaign)

@app.post("/campaigns/{campaign_id}/resume")
def resume_campaign(campaign_id: int, user=Depends(admin), db=Depends(database)):
    settings = locked_settings(db)
    campaign = get_campaign(db, campaign_id)
    if settings.emergency_stop or campaign.status != "paused" or not campaign.approved_by or campaign.approval_digest != digest(campaign):
        raise HTTPException(409, "Clear emergency stop and confirm approved paused campaign")
    uncertain = db.scalar(select(func.count()).select_from(Message).join(Recipient).where(Recipient.campaign_id == campaign_id, Message.state == "uncertain"))
    if uncertain:
        raise HTTPException(409, "Reconcile uncertain deliveries first")
    campaign.status, campaign.pause_reason = "scheduled", ""
    campaign.scheduled_at = max(campaign.scheduled_at or now(), now())
    audit(db, user, "campaign_resumed", campaign_id)
    db.commit()
    return view(campaign)

@app.post("/campaigns/{campaign_id}/cancel")
def cancel_campaign(campaign_id: int, user=Depends(current_user), db=Depends(database)):
    locked_settings(db)
    campaign = get_campaign(db, campaign_id)
    if campaign.status in {"completed", "cancelled"}:
        raise HTTPException(409, "Campaign is terminal")
    campaign.status = "cancelled"
    for message in db.scalars(select(Message).join(Recipient).where(Recipient.campaign_id == campaign_id, Message.state.in_(["queued", "retry"]))):
        message.state = "cancelled"
    audit(db, user, "campaign_cancelled", campaign_id)
    db.commit()
    return view(campaign)

@app.post("/campaigns/{campaign_id}/preview")
def preview(campaign_id: int, data: Preview, user=Depends(current_user), db=Depends(database)):
    c, customer = get_campaign(db, campaign_id), get_customer(db, data.customer_id)
    return {"subject": render(c.subject, customer, c), "body": render(c.body, customer, c),
            "followups": [{"subject": render(x["subject"], customer, c), "body": render(x["body"], customer, c)} for x in c.followups],
            "footer": "The server appends your postal address and an unsubscribe link."}

@app.post("/ai/generate")
def ai_generate(data: Generate, user=Depends(current_user), db=Depends(database)):
    rate_limit("ai:" + str(user.id), 20, 3600)
    settings = db.get(Settings, 1)
    if not settings or not settings.gemini_key:
        raise HTTPException(422, "Configure a Gemini API key")
    campaign = get_campaign(db, data.campaign_id)
    customer = get_customer(db, data.customer_id) if data.customer_id else None
    from integrations.gemini import generate
    try:
        result = generate(decrypt(settings.gemini_key), config().gemini_model,
            business={"product_name": campaign.product_name, "service_description": campaign.service_description},
            customer={k: getattr(customer, k) for k in ("full_name", "company_name", "business_category", "country")} if customer else {},
            instruction=data.instruction, language=data.language)
    except Exception:
        raise HTTPException(502, "AI generation failed; review Gemini configuration and retry")
    counter = db.scalar(select(Counter).where(Counter.name == "ai_generated").with_for_update())
    if counter is None:
        counter = Counter(name="ai_generated", value=0)
        db.add(counter)
    counter.value += 1
    audit(db, user, "ai_generated", campaign.id)
    db.commit()
    return {**result, "requires_human_review": True}

@app.get("/settings")
def settings_get(user=Depends(current_user), db=Depends(database)):
    settings = db.get(Settings, 1)
    if not settings:
        raise HTTPException(503, "Initialize settings")
    return {**view(settings, ("gemini_key", "brevo_key")), "gemini_configured": bool(settings.gemini_key), "brevo_configured": bool(settings.brevo_key)}

@app.put("/settings")
def settings_put(data: SettingsInput, user=Depends(admin), db=Depends(database)):
    settings = locked_settings(db)
    # Timezone and quota changes during an active day could reset or bypass the ledger.
    if settings.timezone != data.timezone:
        active = db.scalar(select(func.count()).select_from(Campaign).where(Campaign.status.in_(["scheduled", "running", "paused"])))
        if active or db.scalar(select(func.count()).select_from(DailyUsage)):
            raise HTTPException(409, "Sending timezone is immutable after scheduling or ledger use")
    values = data.model_dump(exclude={"gemini_key", "brevo_key"})
    identity_changed = any(getattr(settings, k) != values[k] for k in ("sender_email", "sender_name", "postal_address"))
    if identity_changed:
        active = db.scalar(select(func.count()).select_from(Campaign).where(Campaign.status.in_(["scheduled", "running", "paused"])))
        if active:
            raise HTTPException(409, "Cancel active campaigns before changing approved sender identity")
    for key, value in values.items():
        setattr(settings, key, str(value) if key == "sender_email" else value)
    for key in ("gemini_key", "brevo_key"):
        value = getattr(data, key)
        if value is not None:
            setattr(settings, key, encrypt(value) if value else "")
    audit(db, user, "settings_updated")
    db.commit()
    return {"saved": True}

@app.post("/settings/emergency-stop", status_code=204)
def emergency_stop(user=Depends(current_user), db=Depends(database)):
    settings = locked_settings(db)
    settings.emergency_stop = True
    for campaign in db.scalars(select(Campaign).where(Campaign.status.in_(["scheduled", "running"]))):
        campaign.status, campaign.pause_reason = "paused", "Emergency stop"
    notify(db, "paused", "Emergency stop activated")
    audit(db, user, "emergency_stop")
    db.commit()

@app.post("/devices", status_code=204)
def register_device(data: DeviceInput, user=Depends(current_user), db=Depends(database)):
    device = db.get(Device, data.token)
    if device:
        device.user_id = user.id
    else:
        db.add(Device(token=data.token, user_id=user.id))
    db.commit()

@app.get("/messages")
def messages(campaign_id: int, user=Depends(current_user), db=Depends(database)):
    return [view(m) for m in db.scalars(select(Message).join(Recipient).where(Recipient.campaign_id == campaign_id).order_by(Message.due_at.desc()).limit(500))]

@app.post("/messages/{message_id}/reconcile")
def reconcile(message_id: str, data: Reconcile, user=Depends(admin), db=Depends(database)):
    locked_settings(db)
    message = db.get(Message, message_id)
    if not message or message.state != "uncertain":
        raise HTTPException(409, "Only uncertain messages may be reconciled")
    # Operator must obtain exact provider ID from Brevo logs. This never resends.
    message.provider_id, message.state = data.provider_id, "accepted"
    audit(db, user, "delivery_reconciled", message_id)
    db.commit()
    return view(message)

@app.get("/analytics")
def analytics(campaign_id: int | None = None, days: int = 30, user=Depends(current_user), db=Depends(database)):
    if not 1 <= days <= 366:
        raise HTTPException(422, "days must be between 1 and 366")
    from zoneinfo import ZoneInfo
    settings = db.get(Settings, 1)
    today = now().astimezone(ZoneInfo(settings.timezone)).date()
    usage = db.get(DailyUsage, (today, 0))
    query = select(Event.kind, func.count(func.distinct(Event.message_id))).join(Message).join(Recipient)
    if campaign_id is not None:
        query = query.where(Recipient.campaign_id == campaign_id)
    counts = dict(db.execute(query.group_by(Event.kind)).all())
    message_query = select(Message.state, func.count()).join(Recipient)
    if campaign_id is not None:
        message_query = message_query.where(Recipient.campaign_id == campaign_id)
    states = dict(db.execute(message_query.group_by(Message.state)).all())
    daily_query = select(func.date(Event.occurred_at), Event.kind, func.count(func.distinct(Event.message_id))).join(Message).join(Recipient).where(Event.occurred_at >= now() - timedelta(days=days))
    if campaign_id is not None:
        daily_query = daily_query.where(Recipient.campaign_id == campaign_id)
    series = [{"date": str(day), "kind": kind, "count": count} for day, kind, count in db.execute(daily_query.group_by(func.date(Event.occurred_at), Event.kind)).all()]
    ai = db.get(Counter, "ai_generated")
    return {"total_customers": db.scalar(select(func.count()).select_from(Customer)),
        "emails_sent_today": counts.get("sent", 0) if campaign_id is not None else db.scalar(select(func.count(func.distinct(Event.message_id))).where(Event.kind == "sent", func.date(Event.occurred_at) == today)),
        "daily_reserved": usage.reserved if usage else 0,
        "remaining_daily_capacity": max(0, min(settings.daily_limit, settings.provider_daily_limit) - (usage.reserved if usage else 0)),
        "delivered": counts.get("delivered", 0), "failed": states.get("failed", 0) + counts.get("hard_bounced", 0),
        "unsubscribed": db.scalar(select(func.count()).select_from(Suppression).where(Suppression.reason == "unsubscribed")),
        "replies": counts.get("replied", 0), "ai_generated": ai.value if ai else 0,
        "events": counts, "message_states": states, "series": series,
        "mailbox_enabled": bool(config().mailbox_host),
        "note": "Sent/delivered/replied metrics use observed events. Reserved capacity includes uncertain and failed attempts."}

@app.get("/analytics/export")
def analytics_export(campaign_id: int | None = None, user=Depends(current_user), db=Depends(database)):
    query = select(Event).join(Message).join(Recipient)
    if campaign_id is not None:
        query = query.where(Recipient.campaign_id == campaign_id)
    rows = [view(e) for e in db.scalars(query)]
    audit(db, user, "analytics_exported")
    db.commit()
    return Response(csv_document(rows, ["id", "message_id", "kind", "occurred_at"]), media_type="text/csv")

@app.get("/audit")
def audit_log(user=Depends(admin), db=Depends(database)):
    return [view(a) for a in db.scalars(select(Audit).order_by(Audit.id.desc()).limit(500))]

@app.post("/webhooks/brevo")
async def brevo_webhook(request: Request, authorization: str = Header(default=""), db=Depends(database)):
    expected = "Bearer " + config().webhook_token
    if not hmac.compare_digest(authorization, expected):
        raise HTTPException(401, "Invalid webhook authentication")
    raw = await request.body()
    if len(raw) > 65536:
        raise HTTPException(413, "Webhook payload too large")
    try:
        payload = json.loads(raw)
    except ValueError:
        raise HTTPException(422, "Invalid JSON")
    if not isinstance(payload, dict):
        raise HTTPException(422, "Expected an event object")
    event_map = {"request": "sent", "delivered": "delivered", "hard_bounce": "hard_bounced",
        "soft_bounce": "soft_bounced", "blocked": "blocked", "spam": "complained", "unsubscribed": "unsubscribed", "invalid_email": "hard_bounced", "deferred": "deferred"}
    kind = event_map.get(payload.get("event"))
    if not kind:
        return {"ignored": True}
    locked_settings(db)
    message = db.scalar(select(Message).where(Message.provider_id == payload.get("message-id")))
    if not message:
        return {"ignored": True, "reason": "Unknown provider message; provider must retry after acceptance is recorded"}
    event_id = hashlib.sha256((str(message.id) + ":" + kind).encode()).hexdigest()
    if db.get(Event, event_id):
        return {"duplicate": True}
    recipient = db.get(Recipient, message.recipient_id)
    customer = db.get(Customer, recipient.customer_id)
    if payload.get("email", "").lower() != customer.email:
        raise HTTPException(422, "Event recipient mismatch")
    db.add(Event(id=event_id, message_id=message.id, kind=kind))
    if kind in {"hard_bounced", "complained", "unsubscribed", "blocked"}:
        suppress(db, customer, "unsubscribed" if kind == "unsubscribed" else kind)
        campaign = db.get(Campaign, recipient.campaign_id)
        if campaign.status in {"running", "scheduled"}:
            campaign.status, campaign.pause_reason = "paused", "Delivery/compliance event: " + kind
            notify(db, "paused", campaign.pause_reason)
    if kind == "soft_bounced":
        # Conservative default: no further follow-ups until operator review.
        suppress(db, customer, "soft_bounced")
    audit(db, None, "provider_event:" + kind, message.id)
    db.commit()
    return {"processed": True}

def unsubscribe_customer(db, message_id, signature):
    if not check_unsubscribe(message_id, signature):
        raise HTTPException(403, "Invalid unsubscribe token")
    locked_settings(db)
    message = db.get(Message, message_id)
    if message:
        recipient = db.get(Recipient, message.recipient_id)
        customer = db.get(Customer, recipient.customer_id)
        suppress(db, customer, "unsubscribed")
        audit(db, None, "unsubscribed", customer.id)
    db.commit()

@app.get("/unsubscribe/{message_id}", response_class=HTMLResponse)
def unsubscribe_form(message_id: str, token: str):
    if not check_unsubscribe(message_id, token):
        raise HTTPException(403, "Invalid unsubscribe token")
    # GET is a confirmation page so mail scanners do not silently unsubscribe.
    return '<html lang="en"><meta name="viewport" content="width=device-width"><title>Unsubscribe</title><body><h1>Email preferences</h1><form method="post"><button type="submit">Unsubscribe from marketing emails</button></form></body></html>'

@app.post("/unsubscribe/{message_id}", response_class=HTMLResponse)
def unsubscribe(message_id: str, token: str, db=Depends(database)):
    unsubscribe_customer(db, message_id, token)
    return "<html><title>Unsubscribed</title><body><h1>You are unsubscribed.</h1><p>No more marketing emails will be sent to this address.</p></body></html>"

@app.post("/campaigns/{campaign_id}/test")
def test_campaign(campaign_id: int, user=Depends(admin), db=Depends(database)):
    settings = locked_settings(db)
    from integrations.brevo import Brevo
    try:
        verified = Brevo(decrypt(settings.brevo_key)).verify_sender(user.email)
    except Exception:
        raise HTTPException(502, "Unable to verify your test address")
    if not verified:
        raise HTTPException(422, "Your account email must be an active verified Brevo sender")
    customer = db.scalar(select(Customer).where(Customer.email == user.email))
    if not customer or not customer.consent_status or db.get(Suppression, email_hash(customer.email)):
        raise HTTPException(422, "Add your verified account email with documented test consent first")
    source = get_campaign(db, campaign_id)
    test = Campaign(name="TEST: " + source.name[:190], product_name=source.product_name,
        service_description=source.service_description, subject="[TEST] " + source.subject,
        body=source.body, daily_limit=1, followups=[], segment="", status="scheduled",
        approved_by=user.id, approved_at=now(), scheduled_at=now())
    db.add(test)
    db.flush()
    test.approval_digest = digest(test)
    recipient = Recipient(campaign_id=test.id, customer_id=customer.id)
    db.add(recipient)
    db.flush()
    db.add(Message(id=str(__import__("uuid").uuid4()), recipient_id=recipient.id))
    audit(db, user, "test_email_approved", test.id)
    db.commit()
    return {"campaign_id": test.id, "recipient": user.email, "status": "scheduled"}
