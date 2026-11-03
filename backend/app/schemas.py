from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator, ConfigDict
from .policy import validate_consent, validate_template

class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")

class Login(Strict):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)

class CustomerInput(Strict):
    full_name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    company_name: str = Field(default="", max_length=200)
    business_category: str = Field(default="", max_length=200)
    country: str = Field(default="", max_length=100)
    language: str = Field(default="en", pattern="^(en|ar|ckb)$")
    consent_status: bool
    consent_timestamp: datetime
    consent_source: str = Field(min_length=1, max_length=2000)
    segment: str = Field(default="", max_length=100)
    preferences: dict[str, bool] = Field(default_factory=lambda: {"marketing": True, "followups": True})
    @model_validator(mode="after")
    def consent(self):
        validate_consent(self.model_dump())
        return self

class Followup(Strict):
    delay_days: int = Field(ge=2, le=90)
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=20000)
    @field_validator("subject", "body")
    @classmethod
    def template(cls, value):
        return validate_template(value)

class CampaignInput(Strict):
    name: str = Field(min_length=1, max_length=200)
    product_name: str = Field(min_length=1, max_length=200)
    service_description: str = Field(min_length=1, max_length=10000)
    segment: str = Field(default="", max_length=100)
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=20000)
    daily_limit: int = Field(default=300, ge=1, le=100000)
    followups: list[Followup] = Field(default_factory=list, max_length=2)
    @field_validator("subject", "body")
    @classmethod
    def template(cls, value):
        if "\r" in value:
            raise ValueError("Carriage returns are not allowed")
        return validate_template(value)
    @model_validator(mode="after")
    def order(self):
        if any(b.delay_days <= a.delay_days for a, b in zip(self.followups, self.followups[1:])):
            raise ValueError("Follow-up delays must increase")
        return self

class Schedule(Strict):
    scheduled_at: datetime
    @field_validator("scheduled_at")
    @classmethod
    def timezone_required(cls, v):
        if v.tzinfo is None:
            raise ValueError("Timezone required")
        return v

class SettingsInput(Strict):
    daily_limit: int = Field(default=300, ge=1, le=100000)
    provider_daily_limit: int = Field(default=300, ge=1, le=100000)
    provider_per_minute: int = Field(default=10, ge=1, le=600)
    timezone: str = "UTC"
    start_hour: int = Field(default=9, ge=0, le=23)
    end_hour: int = Field(default=17, ge=1, le=24)
    sender_email: EmailStr
    sender_name: str = Field(min_length=1, max_length=200)
    postal_address: str = Field(min_length=5, max_length=1000)
    dns_confirmed: bool = False
    emergency_stop: bool = True
    language: str = Field(default="en", pattern="^(en|ar|ckb)$")
    notifications_enabled: bool = True
    gemini_key: str | None = Field(default=None, max_length=500)
    brevo_key: str | None = Field(default=None, max_length=500)
    @model_validator(mode="after")
    def valid(self):
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError:
            raise ValueError("Unknown IANA timezone")
        if self.start_hour >= self.end_hour:
            raise ValueError("Sending hours must be an increasing same-day window")
        return self

class Generate(Strict):
    campaign_id: int
    customer_id: int | None = None
    instruction: str = Field(default="Create a professional introduction", max_length=2000)
    language: str = Field(default="en", pattern="^(en|ar|ckb)$")

class Preview(Strict):
    customer_id: int

class DeviceInput(Strict):
    token: str = Field(min_length=10, max_length=500)

class PasswordChange(Strict):
    old_password: str
    new_password: str = Field(min_length=12, max_length=128)

class Preferences(Strict):
    marketing: bool = True
    followups: bool = True
    segment: str = Field(default="", max_length=100)

class Reconcile(Strict):
    provider_id: str = Field(min_length=1, max_length=300)
