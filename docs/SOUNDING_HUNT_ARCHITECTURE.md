# Sounding Hunt technical inventory and rollout plan

## Inventory

| Area | Reuse/change | Implementation |
|---|---|---|
| Android identity | Preserve | `app.wxspot.beta`, version/update settings, and existing signing configuration remain unchanged |
| Android UI | Replace primary shell | `MainActivity` now launches Sounding Hunt; new four-tab Compose game shell replaces legacy weather navigation |
| Sounding chart | Reuse/refine | Existing interactive Skew-T/log-P and wind-barb renderer, with public AGL height projection and reset control |
| Map | Reuse | Existing MapLibre service style; new pin/answer markers and result line; tap to place/reposition and signed coordinate inputs |
| Guest identity | Reuse | Existing guest provisioning, bearer session, encrypted resume key, and quotas |
| API | Extend | New `wxspot.sounding_hunt` routes and explicit public/reveal DTOs; legacy endpoints remain available during rollback window |
| IGRA | Reuse/refine | Existing IGRA 2.2 parser; station state, source archive checksum, candidate quality filtering, and bounded queue ingest added |
| Database | Add | Alembic `0006_sounding_hunt`; no old table or row is changed or deleted |
| Worker | Extend | Existing bounded Railway worker runs queue maintenance periodically; no new microservice or queue infrastructure |
| Hosting/storage | Preserve | Railway API, worker, PostGIS, and media bucket remain deployed and unchanged in this branch |

## API contract summary

All game routes use `/game/sounding-hunt` and require the existing guest bearer session. `/today` returns the current sanitized public challenge. `/daily/{day}` returns a sanitized historical/review chart only after its release time. Guess endpoints return the result after persisting the guess. `/daily/{day}/result` reveals a previous day's answer or the requesting player's authorized result. `/leaderboard/{day}`, `/profile`, and practice routes expose only the caller's allowed data. `/admin/*` requires moderator/superuser authorization.

Official daily submissions are unique per player/challenge in PostgreSQL. Practice sessions are unranked and locked during submission. The API scores with `pyproj.Geod(ellps="WGS84")`; challenge rows pin formula version and scale. Ranking order is score, distance, submission time, then user UUID.

## Migration and rollback

The migration adds only game-owned tables/indexes. No migration is applied to production in this work. A code rollback redeploys the prior application/worker while retaining revision `0006`; its tables are not removed. The old Android package/signing lineage and legacy production backend remain available through the validation window. No infrastructure decommissioning is part of this release.

## Operational gate

Do not roll out the game client until the production or staging worker has prepared an active challenge and approximately 14 upcoming verified challenges, and a moderator has reviewed candidate status. If IGRA is unavailable, existing published profiles continue to serve; the worker retries and never publishes fabricated profiles. If the pool is too low, the API reports the challenge unavailable rather than silently substituting synthetic data.

## Validation plan

Run backend pytest and Ruff, Android unit tests and release build, then GitHub Actions. On staging, upgrade from revision `0005`, verify the public DTO, submit and retry an official guess, inspect rank/profile, play repeated practice, wait across daily rollover, and simulate an upstream timeout. On an Android device, verify signing update, guest restore, chart touch/reset, map placement, confirmation, result, lifecycle, and network recovery. Only after these gates pass may Railway production rollout be considered.
