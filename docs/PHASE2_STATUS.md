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

## Automated verification passed

On commit `44aa8dd`:

- Backend CI passed Ruff, the Alembic upgrade, 108 tests, and five live NOAA/NWS source checks: [run 37947621660](https://github.com/michaelhmiv/WxSpot/actions/runs/37947621660).
- Android CI passed formatting, unit tests, instrumentation compilation, lint, debug/release builds, and package-configuration checks: [run 37947621648](https://github.com/michaelhmiv/WxSpot/actions/runs/37947621648).
- The complete daily-to-practice journey passed on Android API 30 and API 36, including ranked result persistence, duplicate rejection, leaderboard, restart recovery, practice scoring, and ranked-statistics isolation: [run 37947621649](https://github.com/michaelhmiv/WxSpot/actions/runs/37947621649).

The emulator package-replacement scenario uses an isolated temporary signer. It checks package and guest-state continuity, but does not verify the production beta signing key. CI produced a review-only debug APK; it is not an update-compatible release artifact.

## Remaining release blockers

- No staging Railway deployment was available in this change. Production migration, service deployment, and candidate queue readiness remain unverified.
- Review migration `0006` against the current production schema, then prepare and review the active and upcoming IGRA queue in staging.
- Verify rollover, source-outage fallback, and operational alerts in staging.
- Verify chart/map gestures, accessibility, offline/error behavior, and update compatibility on a physical Android device.
- The existing beta keystore is not in the development workspace, so a compatible signed release APK cannot be produced here.

Production Railway services and data have not been modified. The feature is not a production release until the checks in [deployment](DEPLOYMENT.md) and [acceptance](ACCEPTANCE.md) pass.


## Sounding Hunt UI test scope

The former `LiveReplayIntegrationTest.kt` exercised Radar, Satellite, Models, Feed, and More navigation, all of which were removed from the new product. That obsolete test was retired with the old UI. `UpgradeAcceptanceTest.kt` validates package identity and guest-session continuity across a package replacement. Its CI signer is temporary and does not verify production signing lineage. The new Sounding Hunt contract tests cover the public challenge DTO and post-submission reveal model. The full automated daily/practice UI journey has passed on API 30 and API 36; physical-device interaction and staging validation remain release gates.
