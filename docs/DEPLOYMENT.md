# Deployment and external service configuration

## Prerequisites

Docker Engine + Compose v2, a publicly reachable HTTPS hostname, PostgreSQL backups, Redis persistence, a Brevo account permitted to send opted-in marketing through its transactional API, a Gemini API project and a verified business identity.

1. Copy `.env.example` to `.env`. Generate unique JWT, unsubscribe and webhook secrets using `python -c "import secrets; print(secrets.token_urlsafe(48))"` separately for each.
2. Generate `ENCRYPTION_KEY` with Fernet as shown in the example. Store it separately from database backups. Losing it makes saved provider credentials unreadable.
3. Set a strong PostgreSQL password in both connection URL and POSTGRES_PASSWORD. URL-encode reserved characters in the database URL password. Set PUBLIC_URL to the final HTTPS API origin without a trailing slash.
4. Leave SENDING_ENABLED=false during setup.
5. Run `docker compose up -d --build`. Migrations run before API/workers start.
6. Provision an admin with the interactive CLI command in README. Operators can be provisioned with `create-operator`. Never put passwords in shell arguments.
7. Put API behind HTTPS on the same host, forwarding to 127.0.0.1:8000. See deployment/Caddyfile. Set request size limits upstream too.
8. Restrict PostgreSQL/Redis to the private container network; the compose file publishes neither port. Run one Beat instance. Worker concurrency is safe because daily accounting uses database locks.
9. Mount a managed secret store/file or restrict .env permissions (0600). Treat Docker administrator access as secret access.

## Brevo

- Obtain a Brevo v3 API key and configure it through Android settings (admin account).
- Add and verify your sender identity in Brevo. The server checks that sender is active when approving campaigns.
- Authenticate the domain with the exact SPF/DKIM records supplied by Brevo, avoiding multiple SPF records.
- Publish DMARC for the From domain, check alignment and review aggregate reports. Set `dns_confirmed` only after independently verifying all records; this checkbox is an operator attestation, not a DNS validation service.
- Configure sender name, physical mailing address, sending timezone/window and actual provider daily/per-minute capacity.
- Use a dedicated provider account or reserve capacity for other systems. The service enforces its own caps and respects provider rejection, but cannot observe unrelated sends made with the same account.
- In Brevo transactional webhooks subscribe to sent/request, delivered, hard/soft bounce, spam, unsubscribed, blocked and invalid_email events.
- Set the target to `https://HOST/webhooks/brevo` with the configured custom authentication header `Authorization: Bearer WEBHOOK_TOKEN`. Do not place tokens in query parameters.
- Confirm your Brevo account supports that authentication configuration. If an intermediary is required, authenticate Brevo at the intermediary and have it inject the internal Bearer credential over TLS; do not expose an unauthenticated endpoint.
- Preserve the original JSON body including `message-id`, `email` and `event`. Retries are idempotent. Unsupported open/click events are ignored.
- Complete an end-to-end event test with your own verified address before live operation. The service appends postal address and signed one-click unsubscribe headers to every message.

## Gemini

Create a Google AI project, enable Gemini API, enable billing/quotas as required, and enter the key in admin settings.
GEMINI_MODEL defaults to gemini-2.5-flash and can be changed to an available model supporting structured JSON output.
Generated content is a draft: review all facts before saving to a campaign and approving.
Model instructions and fact-limited inputs reduce invented claims; they do not prove factual accuracy.
Customer fields sent for personalization go to Google. Establish the required data-processing permissions.

## Authorized mailbox reply tracking

Reply tracking is off unless MAILBOX_HOST/USER/PASSWORD are configured.
Use the actual Reply-To/From mailbox with a TLS IMAP endpoint (port 993), an app password or service credential and only the required mailbox permissions.
The first poll starts from UIDNEXT and ignores existing historical mail.
Subsequent polls match outgoing provider message IDs against In-Reply-To/References and the recipient's sender email.
Mailbox vendors that rewrite/remove these headers require a provider-specific adapter.
Automatic responders with Auto-Submitted other than "no" do not count as customer replies.
Do not claim reply tracking is enabled merely because the mailbox hostname is configured; verify a real authorized test reply.

## Firebase Cloud Messaging

Create a Firebase Android application with package com.aiemail.os.
Place its non-secret client configuration google-services.json in android-app/app/ before building; it is intentionally not in the repository.
For CI, provision that configuration as a protected environment file.
Mount the Firebase service-account JSON read-only into the worker and set GOOGLE_APPLICATION_CREDENTIALS to its path. Do not put a service-account key in the APK.
Add a compose override volume, for example `./secrets/firebase.json:/run/secrets/firebase.json:ro`.
Enable Android notification permission. The app registers its token only after login.
Backend notification rows remain pending if Firebase is unconfigured or no valid devices exist.
Outbox delivery is at least once: a worker interruption can produce a repeated notification, but cannot duplicate a marketing email.

## Activation

Configure approved business facts, import only documented opted-in recipients, preview content and submit the draft.
Administrator approval snapshots eligible recipients and signs a content digest.
Set SENDING_ENABLED=true, restart API/workers/Beat with `docker compose up -d --force-recreate api worker beat`, clear emergency stop in settings and explicitly schedule the approved campaign.
Approval is mandatory and cannot be disabled by a client flag.
Test-send is an explicit admin action, sends only to the logged-in account's Brevo-verified sender address, requires documented consent, consumes normal capacity, and has no follow-ups.

## Operations

- Health endpoint checks PostgreSQL and Redis. Inspect Celery/Beat health and queue depth separately.
- Alert on paused/uncertain messages, growing notification backlog, worker failures and missing provider webhooks.
- An ambiguous send is intentionally not retried. Find its exact provider ID using Brevo logs, call POST /messages/{id}/reconcile with provider_id, then review/resume. Never use a fabricated ID.
- If Brevo confirms no acceptance, keep the original uncertain record for audit and cancel that campaign. Create a new explicitly approved campaign for any desired resend after checking consent and quota.
- Emergency stop serializes with dispatch and pauses running/scheduled campaigns.
- Back up PostgreSQL and server encryption/HMAC keys securely; test restoration. Preserve suppression hashes permanently unless your legally reviewed retention policy requires otherwise.
- Personal-data deletion removes contact/message/event records; non-identifying audit IDs and suppression hashes remain for compliance. Exports should be handled as sensitive personal data.
- Rotate JWT keys to invalidate all sessions. Rotate provider keys through settings. Keep unsubscribe HMAC stable so previously delivered unsubscribe links continue working.
- This repository is a deployment implementation; conduct operational, security, localization/accessibility and legal review for your jurisdiction before production use.
