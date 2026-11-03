from datetime import datetime, timezone
from sqlalchemy import String, Text, Integer, Boolean, DateTime, Date, ForeignKey, UniqueConstraint, JSON
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

def now():
    return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20), default="operator")
    disabled: Mapped[bool] = mapped_column(default=False)
    token_version: Mapped[int] = mapped_column(default=0)

class Settings(Base):
    __tablename__ = "settings"
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    daily_limit: Mapped[int] = mapped_column(default=300)
    provider_daily_limit: Mapped[int] = mapped_column(default=300)
    provider_per_minute: Mapped[int] = mapped_column(default=10)
    timezone: Mapped[str] = mapped_column(String(100), default="UTC")
    start_hour: Mapped[int] = mapped_column(default=9)
    end_hour: Mapped[int] = mapped_column(default=17)
    sender_email: Mapped[str] = mapped_column(String(320), default="")
    sender_name: Mapped[str] = mapped_column(String(200), default="")
    postal_address: Mapped[str] = mapped_column(Text, default="")
    dns_confirmed: Mapped[bool] = mapped_column(default=False)
    emergency_stop: Mapped[bool] = mapped_column(default=True)
    language: Mapped[str] = mapped_column(String(8), default="en")
    notifications_enabled: Mapped[bool] = mapped_column(default=True)
    gemini_key: Mapped[str] = mapped_column(Text, default="")
    brevo_key: Mapped[str] = mapped_column(Text, default="")

class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320), unique=True)
    company_name: Mapped[str] = mapped_column(String(200), default="")
    business_category: Mapped[str] = mapped_column(String(200), default="")
    country: Mapped[str] = mapped_column(String(100), default="")
    language: Mapped[str] = mapped_column(String(8), default="en")
    consent_status: Mapped[bool] = mapped_column(default=False)
    consent_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consent_source: Mapped[str] = mapped_column(Text, default="")
    subscription_status: Mapped[str] = mapped_column(String(30), default="subscribed")
    segment: Mapped[str] = mapped_column(String(100), default="")
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)
    last_email_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class Suppression(Base):
    __tablename__ = "suppressions"
    email_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    reason: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Campaign(Base):
    __tablename__ = "campaigns"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    product_name: Mapped[str] = mapped_column(String(200))
    service_description: Mapped[str] = mapped_column(Text)
    segment: Mapped[str] = mapped_column(String(100), default="")
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    daily_limit: Mapped[int] = mapped_column(default=300)
    status: Mapped[str] = mapped_column(String(30), default="draft")
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approval_digest: Mapped[str] = mapped_column(String(64), default="")
    followups: Mapped[list] = mapped_column(JSON, default=list)
    pause_reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Recipient(Base):
    __tablename__ = "recipients"
    __table_args__ = (UniqueConstraint("campaign_id", "customer_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"))
    replied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (UniqueConstraint("recipient_id", "sequence"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    recipient_id: Mapped[int] = mapped_column(ForeignKey("recipients.id", ondelete="CASCADE"))
    sequence: Mapped[int] = mapped_column(default=0)
    state: Mapped[str] = mapped_column(String(30), default="queued")
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    provider_id: Mapped[str | None] = mapped_column(String(300), unique=True)
    attempts: Mapped[int] = mapped_column(default=0)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str] = mapped_column(Text, default="")

class DailyUsage(Base):
    __tablename__ = "daily_usage"
    day: Mapped[datetime] = mapped_column(Date, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reserved: Mapped[int] = mapped_column(default=0)

class Event(Base):
    __tablename__ = "events"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(30))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Audit(Base):
    __tablename__ = "audit"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(100))
    target: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Device(Base):
    __tablename__ = "devices"
    token: Mapped[str] = mapped_column(String(500), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(50))
    text: Mapped[str] = mapped_column(Text)
    delivered: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Counter(Base):
    __tablename__ = "counters"
    name: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[int] = mapped_column(default=0)
