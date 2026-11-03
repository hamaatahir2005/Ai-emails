import hashlib
import json
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from email_validator import validate_email

VARIABLES = {"customer_name", "company_name", "business_category", "country", "product_name", "service_description"}

def normalize_email(value):
    return validate_email(value.strip(), check_deliverability=False).normalized.lower()

def validate_consent(row):
    if str(row.get("consent_status", "")).lower() not in {"true", "1", "yes"}:
        raise ValueError("Documented opt-in is required")
    if not str(row.get("consent_source", "")).strip():
        raise ValueError("Consent source is required")
    stamp = row.get("consent_timestamp")
    if isinstance(stamp, str):
        stamp = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    if not isinstance(stamp, datetime) or stamp.tzinfo is None or stamp > datetime.now(timezone.utc):
        raise ValueError("Consent timestamp must be timezone-aware and in the past")
    return stamp

def validate_template(text):
    unknown = set(re.findall(r"{{\s*(\w+)\s*}}", text)) - VARIABLES
    if unknown:
        raise ValueError("Unknown template variables: " + ", ".join(sorted(unknown)))
    # Reject any leftover malformed braces too.
    cleaned = re.sub(r"{{\s*(\w+)\s*}}", "", text)
    if "{{" in cleaned or "}}" in cleaned:
        raise ValueError("Malformed template variable")
    return text

def render(text, customer, campaign):
    values = {"customer_name": customer.full_name, "company_name": customer.company_name,
              "business_category": customer.business_category, "country": customer.country,
              "product_name": campaign.product_name, "service_description": campaign.service_description}
    validate_template(text)
    return re.sub(r"{{\s*(\w+)\s*}}", lambda m: values[m[1]], text)

def digest(campaign):
    data = {key: getattr(campaign, key) for key in ("name", "product_name", "service_description", "segment", "subject", "body", "daily_limit", "followups")}
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

def in_window(settings, at):
    hour = at.astimezone(ZoneInfo(settings.timezone)).hour
    return settings.start_hour <= hour < settings.end_hour

def eligible(customer, suppressed, replied=False, followup=False):
    return bool(customer.consent_status and customer.consent_timestamp and customer.consent_source.strip()
        and customer.subscription_status == "subscribed" and not suppressed and not replied
        and customer.preferences.get("marketing", True)
        and (not followup or customer.preferences.get("followups", True)))
