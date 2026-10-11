# Sounding Hunt implementation checkpoint

The game-first Android shell, daily/practice flows, sanitized game APIs, versioned distance scoring, additive database migration, bounded IGRA queue maintenance, and updated product/operations docs are implemented on the Sounding Hunt branch.

The previous native Skew-T/log-P interaction, wind-barb rendering, MapLibre foundation, Android identity/signing settings, guest session, FastAPI service, database, worker, and Railway deployment remain the basis of the application. Production has not been changed.

## Before a release

- GitHub backend and Android checks must pass.
- Staging must migrate from revision `0005`, fill/review a real IGRA queue, and complete all daily, practice, leaderboard, rollover, auth, and fallback checks.
- The beta build must be installed and updated on a physical device with the established signer and `app.wxspot.beta` ID.
- Chart/map interaction, lifecycle recovery, accessibility, and offline/error behavior need a device check.

Prior CI passed backend checks and the two-emulator player journey. A new playful visual redesign and independent Railway staging are underway; staged real-data/API gameplay acceptance passed on 2026-10-09. Final Android post-redesign CI and real-device visual acceptance are not yet claimed. The existing beta keystore is still unavailable here; no update-compatible signed release artifact or production deployment is claimed. See [deployment gates](DEPLOYMENT.md) and [status](PHASE2_STATUS.md).
