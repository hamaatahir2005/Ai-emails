# Testing and Android builds

## Backend

Use a dedicated PostgreSQL test database named emailos_test and a dedicated Redis DB.
The test fixture refuses to run against a database without that prefix.
Every external provider call is blocked by an autouse fixture unless a test replaces it with a controlled adapter response. No live marketing email is sent by tests.

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements.txt
export TEST_DATABASE_URL=postgresql+psycopg://emailos:YOUR_TEST_PASSWORD@localhost:5432/emailos_test
export REDIS_URL=redis://localhost:6379/15
python -m pytest tests -q
```

CI separately applies the initial migration and checks schema drift, then runs policy, API, worker, adapter and concurrent quota tests.
The tests cover CSV/XLSX consent/duplicate imports, JWT/role checks/revocation, unapproved scheduling, unsubscribe/deletion/reimport protection, webhook authentication/replay/out-of-order events, daily quota races, rate limiting, retry backoff, uncertain acceptance, scheduler dispatch, worker recovery, approved follow-ups and Gemini/Brevo request contracts.
Adapter tests validate local contracts only. Real provider credentials and configured webhooks/mailbox/FCM require controlled end-to-end testing with developer-owned addresses.

## Android

Requirements: JDK 17, SDK platform 35, build-tools 35.0.0, platform-tools, Gradle 8.11.1.
The checked-in gradlew is a transparent bootstrap requiring installed Gradle; run the wrapper task to generate the standard distribution wrapper and JAR.

```sh
sdkmanager "platform-tools" "platforms;android-35" "build-tools;35.0.0"
cd android-app
gradle wrapper --gradle-version 8.11.1
./gradlew assembleDebug lintDebug assembleDebugAndroidTest -PBACKEND_URL=https://YOUR_API_HOST/
./gradlew connectedDebugAndroidTest
```

Connect an Android 10+ device/emulator for the last command.
The navigation test uses the production navigation scaffold with a pure local content fixture; it does not fake provider metrics or inject production mock services.
CI uploads debug APK only if that file exists; emulator UI results are separate from compilation results.
The application contains no native binaries and supports ARM64 devices; ABI filters also allow ARMv7 and x86_64.

## Signed release

Create a developer-owned Android signing keystore outside the repository.
Configure the GitHub environment android-release with:
ANDROID_KEYSTORE_BASE64, ANDROID_KEYSTORE_PASSWORD, ANDROID_KEY_ALIAS, ANDROID_KEY_PASSWORD.
Restrict access to that environment.
Run Signed Android release with the final HTTPS backend URL (trailing slash required).
The workflow decodes the keystore in runner temporary storage, builds app-release.apk, uploads it, then deletes signing material.
Signing credentials are never committed or embedded in source.
A release build is not distributed to users automatically.

## Available-environment verification

The editing workspace is read-only, has Python and Java 21, and did not expose Gradle or an Android SDK at inspected paths.
Source is written through the authorized GitHub connector and CI provides PostgreSQL/Redis/Android tooling.
Refer to the actual GitHub Actions run and artifact listing for build/test results; configuration files alone do not establish that an APK exists.
