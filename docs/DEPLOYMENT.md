# Development and deployment

## Local backend

Run `docker compose -f infra/compose.yaml up --build` from the repository root. The API listens on port 8000 and uses persistent development PostGIS and media volumes. Startup applies the immutable initial Alembic migration. Read the interactive API contract at `http://localhost:8000/docs`.

For Python development, use Python 3.12+, install `pip install -e 'backend[test]'`, set `DATABASE_URL` to a real PostGIS database, then run from `backend`: `alembic upgrade head`, `ruff check .`, `ruff format --check .`, and `pytest -q`. The sample `.env.example` contains local defaults only. Tests replace upstream weather and media adapters explicitly; production has no fixture fallback.

## Android

Use JDK 17, Android SDK platform 37.2, build tools 36.0.0, and the checked-in Gradle 9.6 wrapper. AGP 9.4 provides built-in Kotlin; the Compose and serialization plugins use Kotlin 2.4.20. Compile SDK 37.2 supports the current Compose BOM. Minimum Android is 8.0 / API 26; target SDK is 36 pending Android 17 behavior validation.

From `android`, run `./gradlew :app:spotlessCheck :app:testDebugUnitTest :app:lintDebug :app:assembleDebug`. GitHub Actions repeats these checks and uploads the debug APK. To edit formatting, use `:app:spotlessApply`.

The default API URL is `https://wxspotapi-production.up.railway.app`. For a local emulator backend, build with `-Pwxspot.apiUrl=http://10.0.2.2:8000`. Debug permits cleartext for local development; release requires HTTPS. Open the project in Android Studio or install the debug APK with `adb install -r app/build/outputs/apk/debug/app-debug.apk`.

`LiveReplayIntegrationTest` requires a reachable actual API and healthy NOAA radar source. It uses two fresh acceptance accounts, a real advertised frame, persisted geographic elements and original context, the preserved image, and subsequent scans. Run `./gradlew :app:connectedDebugAndroidTest` on an emulator/device. Ordinary unit tests require neither a device nor a live source.

## Railway

The WxSpot project contains `WxSpotAPI`, `PostGIS`, and `WxSpotMedia`. The API builds the root Dockerfile, runs Alembic before Uvicorn, binds `PORT`, and exposes `/health` for readiness. PostGIS uses `postgis/postgis:16-3.5` with a persistent data volume and private networking. The media bucket supplies S3-compatible access through variable references. No credentials are checked into GitHub.

Required API secret configuration: `DATABASE_URL`, `S3_ENDPOINT`, `S3_BUCKET`, `S3_REGION`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, and `ENVIRONMENT=production`. Production refuses to start with incomplete durable media configuration. `NWS_USER_AGENT` and `BASEMAP_TILES` are configurable. To move hosting, use any PostGIS instance and compatible object store; social logic contains no Railway API dependency.

Migrations run before accepting requests. The initial migration is frozen SQL, independent of evolving ORM definitions. Add subsequent Alembic revisions for schema changes. This first release uses one API replica. Add a migration deployment job before increasing replicas.

## Operations and release gates

Keep database and object-store backups, exercise restores, monitor `/health`, HTTP errors, upstream source states, and capture failures. Monitor the bucket's growth: every published layer retains an approximately 1024-pixel raw weather raster. Soft deletion preserves moderation evidence and media; define retention before large public use. Failed multi-step publication can leave unreferenced objects; a lifecycle cleanup job is Phase 2.

Moderator authority is assigned through trusted database administration, never through sign-up or a mobile toggle. After independently confirming an account's email, set its `is_moderator` flag in a privileged database session. Moderators inspect `/moderation/reports` and submit `/moderation/actions` using their authenticated session; every action records actor, reason, previous/new status, and timestamp.

Before unrestricted public launch, configure email verification and account recovery, replace the low-volume OSM tile default with suitable production tile hosting, establish moderation coverage and retention, validate target Android 17 behavior, and provide a release signing key through secret infrastructure. The downloadable debug build is for reviewing the vertical slice, not a Play Store signed release.
