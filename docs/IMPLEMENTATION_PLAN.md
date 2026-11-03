# Implementation plan
1. Inspect existing repository (empty at start); initialize a feature branch.
2. Implement relational schema, migrations, authentication and immutable consent/suppression checks.
3. Implement customer import/export, campaign approval and lifecycle APIs.
4. Implement server-side Celery scheduling, atomic daily reservations, retry/reconciliation policy and Brevo/Gemini adapters.
5. Implement provider events, unsubscribe, mailbox reply detection and push delivery.
6. Implement Kotlin Compose client, Keystore session storage, Retrofit, Room, Hilt, localization and navigation tests.
7. Add PostgreSQL/Redis integration tests, CI APK builds, release signing and deployment documentation.
8. Validate available tooling; report external configuration and unverified behavior explicitly.
