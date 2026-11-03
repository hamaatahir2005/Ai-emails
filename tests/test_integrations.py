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
