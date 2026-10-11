# Architecture

## Runtime

```text
Android app (Compose + MapLibre)
           │ HTTPS + retained guest session
           ▼
Existing FastAPI modular monolith ─── PostgreSQL/PostGIS
           ▲                              │
           │                              │ validated candidates/results
Existing bounded Railway weather worker ┘
           │
           └── NOAA/NCEI IGRA 2.2, bounded station downloads
```

The game is a separate backend module (`wxspot.sounding_hunt`) with explicit public and reveal response models. It uses the existing authentication, quota, database session, Alembic, worker, weather provider, and MapLibre infrastructure. No new service, queue product, cache service, or per-request weather processing is introduced.

## Main components

- **Retained:** Android application ID and beta signing path; guest identity/session vault; Material 3; native Skew-T/log-P chart and touch interaction; MapLibre; FastAPI; PostgreSQL/PostGIS; Alembic; IGRA parser; MetPy utilities; WGS84 `pyproj.Geod`; existing Railway API, worker, database, and object storage.
- **Added:** game screens and DTOs; server-authoritative scoring, Eastern challenge calendar, result/statistics/leaderboard/practice APIs; private station, observation, ingestion-status, challenge, guess, and practice tables; periodic queue maintenance in the current worker.
- **No longer primary UI:** radar, satellite, model, observation, and community navigation. **Not removed from the platform:** weather provider and rendering routes, model/radar/satellite data pathways, existing workers and retained observations. These remain available for future weather-powered game modes, and for rollback.

## UI design architecture (pending implementation)

The current Kotlin Compose implementation is visually dark/Material-oriented. The next implementation pass must introduce WXspot light-first semantic theme tokens, reusable game components and original art, reorganize the game screens, and use a distinct light map style without overwriting weather-analytics map style behavior. Preserve game-scoring and data contracts. See [visual redesign implementation plan](WXSPOT_GAME_VISUAL_REDESIGN_PLAN.md). This section describes required work, not completed functionality.

## Data flow

The worker fetches the official station inventory, filters CONUS stations, and downloads at most three recent station archives per maintenance cycle. The existing provider parses IGRA fixed-width records and preserves QC flags, pressure in hPa, wind in m/s, and dew point temperature derived from the published dew point depression or valid relative humidity. Candidate validation is performed before storage. Challenge publication is transactional and unique by day and observation.

The pre-guess API projects only timestamp, surface pressure, and chart levels. Heights are returned as AGL, not MSL, to avoid disclosing station elevation. Guess coordinates are validated, distance is calculated on the server with WGS84, and results are revealed only after a stored official guess or when the challenge has closed. Practice cannot select an observation reserved for an active or future daily challenge.

## Database migration

Alembic revision `0006_sounding_hunt` adds tables and indexes only. It does not alter or delete legacy user, weather, media, or community data. Daily uniqueness is enforced at the database level. Scoring version and scale are stored with published challenges and submissions.

For rollback, redeploy the previous application/worker revision and leave the additive tables in place. Do not run the migration downgrade in production; the new tables may contain valid player results. Any cleanup is a separate reviewed migration after an explicit data-retention decision.

## Security boundaries

- A guest bearer token is required for game requests; the existing resume key remains in the encrypted Android session vault.
- Public and private response models are separate. The public challenge does not serialize ORM rows.
- Guess data are final and unique. The leaderboard reports score/distance only, not coordinates.
- Admin candidate inspection/exclusion requires moderator or superuser authorization.
- Quotas apply to daily attempts, practice creation, and practice submission. Inputs reject extra fields, nonfinite values, and out-of-range coordinates.
- IGRA observations are public data. This design prevents trivial app-level answer leakage; it does not claim that a determined player cannot compare a chart with NOAA archives.

## Operations

The existing worker runs game maintenance every 15 minutes with one in-process lock, bounded downloads, and a small batch. It logs validated-candidate and upcoming-challenge counts and warns when the queue is below three or the candidate pool below five. The admin endpoints expose candidate validation and queue status. The existing worker and API health checks remain unchanged.

The current production database and object-storage bucket remain intact. Radar/model/weather-worker simplification or decommissioning is deferred until the Sounding Hunt release has passed staging and rollback gates.
