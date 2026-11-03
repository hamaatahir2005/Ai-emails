from datetime import datetime, timezone
from types import SimpleNamespace
import pytest
from backend.app.policy import validate_consent, normalize_email, validate_template, render, in_window, eligible, digest

def test_email_normalization():
    assert normalize_email(" A.User@EXAMPLE.COM ") == "a.user@example.com"

@pytest.mark.parametrize("updates", [
    {"consent_status": False}, {"consent_source": ""},
    {"consent_timestamp": "2099-01-01T00:00:00Z"}, {"consent_timestamp": "2025-01-01T00:00:00"}])
def test_consent_rejects_missing_evidence(contact, updates):
    with pytest.raises(ValueError):
        validate_consent({**contact, **updates})

@pytest.mark.parametrize("text", ["{{discount}}", "{{customer_name", "{{broken-name}}"])
def test_unsupported_variables(text):
    with pytest.raises(ValueError):
        validate_template(text)

def test_render_does_not_recursively_evaluate_customer_input():
    customer = SimpleNamespace(full_name="{{product_name}}", company_name="", business_category="", country="")
    campaign = SimpleNamespace(product_name="Example", service_description="Approved")
    assert render("Hi {{customer_name}}", customer, campaign) == "Hi {{product_name}}"

def test_sending_window_timezone():
    settings = SimpleNamespace(timezone="Asia/Baghdad", start_hour=9, end_hour=17)
    assert in_window(settings, datetime(2026, 1, 1, 6, tzinfo=timezone.utc))
    assert not in_window(settings, datetime(2026, 1, 1, 14, tzinfo=timezone.utc))

def test_followups_respect_preferences():
    customer = SimpleNamespace(consent_status=True, consent_timestamp=datetime.now(timezone.utc), consent_source="signup",
        subscription_status="subscribed", preferences={"followups": False})
    assert eligible(customer, False)
    assert not eligible(customer, False, followup=True)
    assert not eligible(customer, True)
    assert not eligible(customer, False, replied=True)
