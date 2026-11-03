# Delivery status and operational scope

The feature branch contains backend, migrations, integrations, workers, Android source, tests, container configuration and build workflows.
See GitHub Actions for actual test/build outcomes.

## External setup required

- HTTPS server and PostgreSQL/Redis deployment.
- Organization admin provisioning and a production Android BACKEND_URL.
- Brevo credentials, active verified sender, SPF/DKIM/DMARC, actual provider capacity and authenticated webhook setup.
- Gemini API credentials and model access; human review of generated claims.
- Optional authorized IMAP mailbox for real reply tracking.
- Firebase client configuration and server credentials for actual push delivery.
- Developer release signing key and protected CI signing secrets.

## Scope and conservative choices

- One organization per deployment; admin/operator roles, no public signup or multi-tenant isolation.
- Brevo is implemented; Amazon SES is not selected for this version.
- Excel means .xlsx; legacy binary .xls is rejected.
- Generated drafts are saved/reviewed before approval. AI is not allowed to silently alter approved content at send time.
- Follow-up drafts can be generated using campaign/customer context and instruction; follow-up sending uses explicitly approved templates, not unreviewed AI output.
- Provider quotas are configured local caps plus provider-enforced rejection, not a promise to know unrelated provider-account usage.
- Unknown acceptance needs manual reconciliation, so correctness may require operator intervention.
- SMTP delivery cannot be recalled after acceptance. Suppression prevents future sends.
- Foreground dashboard refresh is every 30 seconds; background sending is server-side and independent of Android.
- Main UI labels have English/Arabic/Sorani resources and RTL; API validation errors and raw provider event/state names remain English technical text.
- Room caches are app-private, not a custom encrypted database. Sensitive tokens use Keystore; service keys live on the backend.
- Missing FCM/mailbox configuration does not produce fabricated notifications/reply metrics.
- Production load testing, provider end-to-end validation, real-device accessibility/RTL review and external security review remain deployment tasks.

## Observed build evidence

Commit 800b13ec0533d0b376ceea43515dd9b3b6ea84d9 was built by GitHub Actions run 41705878025:
- Backend: 38 tests passed; Alembic reported no schema drift.
- Android: assembleDebug, lintDebug and assembleDebugAndroidTest succeeded.
- A real app-debug APK artifact was uploaded (artifact ID 13264429730).
- Emulator navigation validation and subsequent hardening commits require their own final CI result.

Artifact URLs and later test results are available in the pull request checks; do not treat this earlier build as validation of untested later commits.
