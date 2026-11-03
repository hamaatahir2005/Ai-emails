import httpx

class RateLimited(Exception):
    pass

class CredentialsError(Exception):
    pass

class UncertainDelivery(Exception):
    pass

class Rejected(Exception):
    pass

class Brevo:
    def __init__(self, key):
        self.key = key

    def request(self, method, path, **kwargs):
        try:
            response = httpx.request(method, "https://api.brevo.com/v3" + path,
                headers={"api-key": self.key, "accept": "application/json"}, timeout=25, **kwargs)
        except httpx.TransportError as exc:
            raise UncertainDelivery("Transport failure; reconcile before any resend") from exc
        if response.status_code in (401, 403):
            raise CredentialsError("Brevo credentials or account need attention")
        if response.status_code == 429:
            raise RateLimited("Brevo rate limit reached")
        if response.status_code >= 500:
            raise UncertainDelivery("Brevo server error; acceptance is unknown")
        if response.is_error:
            raise Rejected("Brevo rejected request with status " + str(response.status_code))
        return response.json()

    def verify_sender(self, email):
        senders = self.request("GET", "/senders").get("senders", [])
        return any(s.get("email", "").lower() == email.lower() and s.get("active") is True for s in senders)

    def send(self, *, message_id, to, name, sender_email, sender_name, subject, text, unsubscribe_url):
        result = self.request("POST", "/smtp/email", json={
            "sender": {"name": sender_name, "email": sender_email},
            "to": [{"email": to, "name": name or to}],
            "subject": subject.replace("\n", " ").replace("\r", " "),
            "textContent": text,
            "headers": {
                "idempotencyKey": message_id,
                "List-Unsubscribe": "<" + unsubscribe_url + ">",
                "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"
            },
            "tags": ["emailos", message_id]})
        if not result.get("messageId"):
            raise UncertainDelivery("Provider response omitted messageId")
        return result["messageId"]
