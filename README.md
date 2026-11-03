# AI Email Marketing OS

Android 10+ application and server-side campaign system for **permission-based** email marketing.
Real adapters call Google Gemini and Brevo; production never falls back to simulated data.

## Run

```sh
git clone -b codex/ai-email-marketing-os https://github.com/hamaatahir2005/Ai-emails.git
cd Ai-emails
cp .env.example .env
# Replace every placeholder with separately generated secrets; keep SENDING_ENABLED=false.
docker compose up -d --build
docker compose run --rm api python -m backend.app.cli create-admin --email you@example.com
```

Read [deployment setup](docs/DEPLOYMENT.md) before enabling sending.
API documentation: `https://YOUR_HOST/docs`; schema: `/openapi.json`.
The Android API origin is configured at build time, not an API key:

```sh
cd android-app
# Requires JDK 17, Android SDK platform 35/build-tools 35.0.0 and Gradle 8.11.1.
gradle wrapper --gradle-version 8.11.1
./gradlew assembleDebug -PBACKEND_URL=https://YOUR_HOST/
```

Expected build output, **only after a successful build**:
`android-app/app/build/outputs/apk/debug/app-debug.apk`.
The [Validate and build workflow](.github/workflows/ci.yml) uploads the actual APK as artifact `app-debug`.
[Signed release workflow](.github/workflows/release.yml) uses environment secrets; no signing key is committed.

## Google sign-in

The Android login screen supports Google Credential Manager. The backend validates Google-signed ID tokens with a single-use nonce and admits only preprovisioned organization accounts. Set the public Web OAuth client ID on the backend and APK, register the actual Android signing SHA-1, and follow [Google sign-in setup](docs/GOOGLE_SIGN_IN.md). Google sign-in requires a live HTTPS backend and does not grant Gmail sending permissions.

## Components

| Directory | Contents |
|---|---|
| android-app | Kotlin, Compose Material 3, Hilt MVVM, Retrofit, Room, Keystore, optional FCM |
| backend | FastAPI, authentication/roles, contacts, consent, campaigns, approvals, analytics |
| database | PostgreSQL schema and versioned Alembic migrations |
| workers | Celery and Beat dispatch, quota reservations, delivery and recovery |
| integrations | Gemini, Brevo, TLS IMAP replies, FCM |
| tests | Policy, API, PostgreSQL concurrency, worker and adapter tests |
| deployment | Container build and HTTPS proxy example |
| docs | Configuration, architecture, operational limits and testing |

## Implemented behavior

- CSV and XLSX imports require opt-in, evidence source and a past timezone-aware timestamp. Duplicates and suppressed addresses are rejected per row.
- Customer search/category/segment filtering, preferences, history, export and personal-data deletion.
- Immutable approved campaign content and recipient snapshot; draft → awaiting approval → scheduled → running → paused/completed/cancelled.
- Default limit 300, organization/campaign/provider caps, IANA timezone and sending window, Redis request limits and durable PostgreSQL reservations.
- Every attempt consumes capacity conservatively. Duplicate tasks do not send again. Unknown acceptance pauses the campaign for reconciliation.
- Up to two approved follow-ups, at least 48 hours apart; unsubscribe, suppression or observed mailbox reply stops queued follow-ups.
- Provider events drive delivery analytics; there are no synthetic opens/clicks/replies.
- One-click unsubscribe POST and scanner-safe confirmation GET; keyed-hash suppression survives personal-data deletion.
- scrypt password hashes, expiring/revocable JWTs, administrator approval, rate limits, encrypted backend provider keys, audit logs and emergency stop.
- Foreground refresh, cached dashboard, interactive day/month chart, dark/light/system appearance and English/Arabic/Sorani resources with RTL.
- Notification outbox for lifecycle/limit/error/reply/credential events and optional FCM delivery.

## Configuration and validation still required

A generated project is not evidence of a validated production deployment. Configure HTTPS, Brevo transactional marketing permission and quota, authenticated sender domain, real opt-in evidence, Gemini billing/model access, and optional mailbox/Firebase credentials. Review [current limits](docs/STATUS.md) and [test instructions](docs/TESTING.md).

The CI APK defaults to `https://localhost/` to avoid embedding an invented production backend. Rebuild with your deployed HTTPS origin before use on a device.
