# Sounding Hunt implementation checkpoint

The game-first Android shell, daily/practice flows, sanitized game APIs, versioned distance scoring, additive database migration, bounded IGRA queue maintenance, and updated product/operations docs are implemented on the Sounding Hunt branch.

The previous native Skew-T/log-P interaction, wind-barb rendering, MapLibre foundation, Android identity/signing settings, guest session, FastAPI service, database, worker, and Railway deployment remain the basis of the application. Production has not been changed.

## Before a release

- GitHub backend and Android checks must pass.
- Staging must migrate from revision `0005`, fill/review a real IGRA queue, and complete all daily, practice, leaderboard, rollover, auth, and fallback checks.
- The beta build must be installed and updated on a physical device with the established signer and `app.wxspot.beta` ID.
- Chart/map interaction, lifecycle recovery, accessibility, and offline/error behavior need a device check.

CI has passed backend tests/lint and live-source checks, Android unit/format/build checks, and the two-emulator player journey. The development workspace itself has no Gradle runtime or Python test dependencies. A review-only debug APK is available from CI, but the existing beta keystore and a staging deployment are not available here; no update-compatible signed release artifact or production deployment is claimed. See [deployment gates](DEPLOYMENT.md) and [status](PHASE2_STATUS.md).
