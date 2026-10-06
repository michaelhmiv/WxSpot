# Architecture

Android Kotlin/Compose/Material 3 hosts a MapLibre Native map in AndroidView. Camera, weather timeline, annotation editing, authentication, and social state live outside the map renderer. The renderer projects saved WGS84 geometry at every draw, so changing zoom, bearing, or radar time cannot displace marks. Manual dependency injection supplies API/auth repositories to a lifecycle ViewModel; pure domain reducers handle replay and editing.

FastAPI is a modular monolith. SQLAlchemy/psycopg access PostgreSQL/PostGIS; Alembic owns migrations. Weather providers, media storage, authentication, and ranking are separate modules. REST/OpenAPI remains platform-neutral. No Redis, distributed queue, or permanent websocket is needed for this slice.

The radar provider reads RIDGE2 WMS capabilities, exposes immutable frame IDs, and creates explicit-time EPSG:3857 tile URLs. A post stores an entire versioned WeatherContext with multiple layers plus WGS84 elements. Publishing also preserves a georeferenced radar raster in S3-compatible storage. This is the unmarked source layer, never a screenshot or flattened annotation. It preserves exact replay after NOAA's short live retention. The viewer can switch from that marked raster to available live frames and return at any time. Historical intermediate scans beyond provider retention require Phase 2 archival ingestion.

Weather failures have explicit states and timestamps. Alert/capabilities caches are bounded, synchronized, and expire independently; no upstream calls are required to read existing social posts. Raster loads report failures and do not present an older image with a newer timestamp. The API validates frame existence before publication and refuses ambiguous archival requests.

## ADR 001: auth without an external setup blocker

Use FastAPI Users 15, an established security-maintained authentication library, isolated behind auth dependencies. Its Argon2 password helper and database bearer strategy handle credential storage and revocable sessions. Domain endpoints only receive the authenticated User. This avoids inventing hashing/token logic or requiring a new Firebase project before the two-account workflow works. The library is in maintenance mode; replacements are restricted to the auth boundary. Sessions expire after seven days and logout revokes them. No client-selected moderator or verified flag is accepted. Email delivery, recovery, and verification are a documented release gate before unrestricted public launch.

## ADR 002: provider retention and exact replay

RIDGE2 advertises approximately two hours at KCLX at inspection. Never send an expired TIME parameter and rely on nearestValue: that could silently show a different scan. Capture the original frame's geographic layer at publication; preserve its frame ID, valid time, bounds, and source. Saved raster availability and live provider availability are separate UI states. All annotation geometry remains vector data.

## ADR 003: discovery and scale

Viewport envelopes use GiST indexes and ST_Intersects, including antimeridian splitting. Status/time/type/author indexes narrow social searches. Rank in SQL through a replaceable strategy; do not retrieve all posts to rank on the phone. Blocks are bidirectional visibility restrictions. Unique database constraints make likes/follows idempotent. A database-backed posting quota works across processes.

## ADR 004: explanation extension boundary

Future educational explanations consume the immutable WeatherContext, geographic elements, and preserved layer through a separate explanation provider. A future post explanation endpoint can resolve those existing entities without changing map replay, storage, authentication, or social ranking. Explanations should return source provenance and distinguish community interpretation from official information. This slice makes no inference-provider calls and exposes no AI-generated weather claims.

## ADR 005: map renderer compatibility

Use MapLibre 13.6.1's explicitly supported OpenGL ES artifact. The default 13.x artifact selects Vulkan; an actual API 30 device test crashed in its native renderer during surface initialization (goldfish shared-memory mapping failure). OpenGL gives this Android 8+ slice a mature renderer with broad device compatibility. The choice applies to both debug and release builds, so the tested renderer is also the delivered renderer. Reconsider Vulkan after physical-device coverage across the intended fleet. See [MapLibre rendering engines](https://maplibre.org/maplibre-native/android/examples/data/rendering-engine/).

## ADR 006: temporary community access without sign-in

The user requested removal of sign-in for the review build. Android therefore creates an ordinary profile automatically through `/auth/guest`. Each installation receives its own high-entropy device credential; the server stores only its SHA-256 digest. The existing FastAPI Users manager creates the user and its database strategy issues the same revocable, seven-day bearer sessions used by ordinary accounts. The device credential and session are encrypted by Android Keystore. Expired sessions renew once through the saved credential, preserving the user ID and ownership. Concurrent requests share one bootstrap operation. Invalid or disabled credentials do not silently create replacement profiles.

The app has no email/password forms or sign-out action. Profile names, notifications, and blocked-user management are available from the profile surface. Existing valid sessions are retained on upgrade. The underlying email/password API remains available for other clients and future account linking. Moderator permissions and verified roles remain server controlled. Device profiles are not transferable through a user-facing recovery flow; clearing app data or reinstalling creates a new profile. See [review access](REVIEW_ACCESS.md).

## Deployment

One API instance, one PostGIS service with persistent volume, and an S3-compatible bucket. Railway uses the repository's Dockerfile and health endpoint. API deployment runs migrations before listening. Production refuses local volatile media. Local docker compose provides PostGIS/API and persistent local media. CI runs real PostGIS integration tests and Android test/lint/build checks.
