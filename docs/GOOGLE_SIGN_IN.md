# Google sign-in setup

Google sign-in authenticates a user to **AI Email Marketing OS**. It does not replace the backend, deploy Railway, grant Gmail sending permission, or configure Brevo/Gemini.

## Google Cloud configuration

1. In Google Cloud Console, create/select your project and configure the Google Auth Platform consent screen, branding, audience and contact information. For an external app in Testing, add the actual Google accounts as test users.
2. Create an OAuth 2.0 **Web application** client. Copy its public client ID, ending in .apps.googleusercontent.com. No Web client secret is required by this ID-token verification flow. No browser redirect URI is used by this native Android Credential Manager flow.
3. Create an OAuth 2.0 **Android** client in the same project. Package: com.aiemail.os. Register the SHA-1 of the signing certificate for the APK you actually install.
4. A successful CI Android build uploads google-android-signing-report, containing the actual APK certificate SHA-1/SHA-256. Register that SHA-1 for that debug APK. CI generates a fresh default debug key on a fresh runner, so a later debug build may require registering a different SHA-1. Use your developer-owned stable release signing key for distributed builds.
5. Google Play services and an eligible Google account must be available on the device. User cancellation returns to the login screen without an error dialog.

## Backend / Railway

Set GOOGLE_WEB_CLIENT_ID to the **Web** client ID, not the Android client ID.
Use the same value for the APK and backend.
Apply migrations before starting the API:

```sh
alembic -c database/alembic.ini upgrade head
```

Provision only authorized organization users. Existing password-provisioned users with matching authoritative Google emails can sign in; the first successful login binds their immutable Google subject.

For a Google-only administrator:

```sh
python -m backend.app.cli create-google-admin --email YOUR_GOOGLE_EMAIL
```

For a Google-only operator:

```sh
python -m backend.app.cli create-google-operator --email OPERATOR_GOOGLE_EMAIL
```

These commands create an unguessable random password and do not print it.
All existing JWT expiry, role checks, disabled-account enforcement and logout revocation also apply to Google sessions.
The server does not automatically admit arbitrary Google users or promote anyone to administrator.
For automatic email-based linking, Google must be authoritative: Gmail/Googlemail or a matching verified Workspace hosted domain. Other externally hosted Google-account email identities are rejected.

## APK / GitHub Actions

Set repository Actions **variables** (these values are public configuration):
- BACKEND_URL: deployed HTTPS API origin ending in /
- GOOGLE_WEB_CLIENT_ID: same Web OAuth client ID as the backend

The debug workflow reads these variables and uploads an APK plus its actual signing certificate report.
Alternatively, build locally:

```sh
gradle -p android-app assembleDebug -PBACKEND_URL=https://YOUR_API_HOST/ -PGOOGLE_WEB_CLIENT_ID=YOUR_WEB_CLIENT_ID.apps.googleusercontent.com
```

Replace the entire ID example with the real Web client ID. The signed release workflow accepts the public Web client ID as an input or uses the repository variable.
If the ID is missing, the Google button remains visible but disabled with a localized configuration explanation. Password sign-in still works. A configured OAuth ID does not fix an unreachable BACKEND_URL.

## Security protocol

1. Android requests a random, five-minute, server-side challenge.
2. Credential Manager presents the explicit Google account sign-in UI and binds the ID token to that nonce.
3. Android sends the ID token and nonce over HTTPS to POST /auth/google.
4. Redis atomically consumes the challenge once. The server verifies Google's RSA signature, expiry, issuer, audience, nonce, verified email and authoritative domain.
5. The server finds a preprovisioned active organization user and binds/checks their stable Google subject under a row lock.
6. The server issues the normal short-lived application JWT. Android stores that JWT in Keystore-backed encrypted session storage. Google ID tokens are never stored in Room, returned to the client, or written to audit logs.

Unapproved/disabled users and changed subjects fail closed. Signing in does not authorize sending campaigns; administrator campaign approval remains mandatory.
The integration requests identity only, not Gmail mailbox/send permissions.

## Validation

Backend tests generate a local RSA key and mock only Google's certificate transport. The real Google verification SDK checks signatures/audience/expiry; tests also cover nonce replay, verified email, unapproved users, stable subject binding, disabled accounts, role escalation and logout.
UI tests exercise the real login composable's enabled/configured/busy states without contacting Google.
Real account-picker and consent-screen validation requires your OAuth project, registered signing certificate, allowed test account and live HTTPS backend.
