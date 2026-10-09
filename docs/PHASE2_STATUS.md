# WXspot delivery status

## Existing Phase 2 foundation

The repository's accepted Phase 2 beta provides the Android application identity/signing lineage, retained guest sessions, FastAPI/PostgreSQL/PostGIS, Railway API/worker, IGRA 2.2 parser, MetPy calculations, native Skew-T/log-P chart, and MapLibre style. Physical-device checks from the original Phase 2 status remain relevant to the update path.

## Sounding Hunt transformation

Implemented on the feature branch:

- New Android Home/Play/Rankings/Profile shell and Daily/Practice flow.
- Existing native sounding renderer reused for mystery profiles, with date/UTC time visible before guessing and AGL chart heights.
- MapLibre guess/reveal display and signed-coordinate entry.
- FastAPI game domain for sanitized challenges, official guesses/results, WGS84 scoring, leaderboard, history, profile statistics, practice, and moderator candidate controls.
- Additive Alembic revision `0006_sounding_hunt`.
- Bounded IGRA validation/queue maintenance in the existing worker.
- Product, architecture, migration, rollback, and acceptance documentation.

## Not release-verified

- GitHub Actions results for the transformation branch.
- Production migration, Railway service deployment, and the 14-day candidate queue.
- Physical Android chart/map, process-restart, accessibility, and update-lineage checks.
- The emulator package-replacement scenario uses an isolated temporary signer and validates app/guest-state continuity only; it does not verify the production beta signing key.
- Compatible signed release artifact; the existing keystore is not in the development workspace.
- Staging end-to-end run, daily rollover, and source-outage fallback.

Production Railway services and data have not been modified. The feature is not a production release until the checks in [deployment](DEPLOYMENT.md) and [acceptance](ACCEPTANCE.md) pass.


## Sounding Hunt UI test scope

The former `LiveReplayIntegrationTest.kt` exercised Radar, Satellite, Models, Feed, and More navigation, all of which were removed from the new product. That obsolete test was retired with the old UI. `UpgradeAcceptanceTest.kt` validates package identity and guest-session continuity across a package replacement. Its CI signer is temporary and does not verify production signing lineage. The new Sounding Hunt contract tests cover the public challenge DTO and post-submission reveal model; full Android UI/device journey coverage remains a CI and staging validation item.
