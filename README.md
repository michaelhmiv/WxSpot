# WXspot — Sounding Hunt

**Read the atmosphere. Find the location.**

WXspot is an Android geography game built around real radiosonde observations. Each day, every player receives the same observed sounding and places one pin on a map of the contiguous United States. The server calculates the official WGS84 distance and score. Unlimited historical practice is unranked.

The Android client remains Kotlin, Jetpack Compose, Material 3, and MapLibre. The API remains the existing FastAPI modular monolith, and the PostgreSQL/PostGIS database and Railway API/worker remain in place. The new game domain is additive and documented in [Sounding Hunt architecture](docs/SOUNDING_HUNT_ARCHITECTURE.md).

## Product scope

The primary navigation is **Home | Play | Rankings | Profile**. The only game modes are Daily Challenge and Unlimited Practice. The old weather and community screens are no longer the app launch experience. Existing backend routes, data, storage, signing lineage, and Railway services are retained during rollout for compatibility and rollback.

## Data source

Challenges use measured IGRA 2.2 radiosonde launches from NOAA/NCEI. The worker downloads a bounded station archive, validates actual pressure-level observations, preserves missing and QC-removed values as null, and publishes only validated, unused profiles. It does not synthesize observations. See [NOAA IGRA](https://www.ncei.noaa.gov/products/weather-balloon/integrated-global-radiosonde-archive).

## Development

- Backend: `cd backend && pip install -e '.[test]' && pytest`
- Backend lint: `cd backend && ruff check wxspot tests && ruff format --check wxspot tests`
- Android: use the repository Gradle wrapper and the existing CI workflows. Keep `app.wxspot.beta`, its versioning, and signing configuration intact for beta updates.
- Local API and Railway deployment details: [Deployment and rollback](docs/DEPLOYMENT.md).

## Release status

Sounding Hunt is under implementation on a dedicated branch. Production Railway services and data have not been changed. Do not roll the branch into production until CI passes, a verified daily challenge queue exists, the existing beta signing key is available for release verification, and the Android journey has been exercised on a device. See [current status](docs/PHASE2_STATUS.md).
