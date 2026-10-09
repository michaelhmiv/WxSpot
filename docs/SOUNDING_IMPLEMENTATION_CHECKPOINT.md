# Sounding Hunt implementation checkpoint

The game-first Android shell, daily/practice flows, sanitized game APIs, versioned distance scoring, additive database migration, bounded IGRA queue maintenance, and updated product/operations docs are implemented on the Sounding Hunt branch.

The previous native Skew-T/log-P interaction, wind-barb rendering, MapLibre foundation, Android identity/signing settings, guest session, FastAPI service, database, worker, and Railway deployment remain the basis of the application. Production has not been changed.

## Before a release

- GitHub backend and Android checks must pass.
- Staging must migrate from revision `0005`, fill/review a real IGRA queue, and complete all daily, practice, leaderboard, rollover, auth, and fallback checks.
- The beta build must be installed and updated on a physical device with the established signer and `app.wxspot.beta` ID.
- Chart/map interaction, lifecycle recovery, accessibility, and offline/error behavior need a device check.

At this checkpoint, the development workspace has no Gradle wrapper/runtime, Python project test dependencies, existing beta keystore, or staging deployment. No release artifact or production deployment is claimed. See [deployment gates](DEPLOYMENT.md) and [status](PHASE2_STATUS.md).
