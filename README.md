# WXspot — Weather Spot

**Flagship game: Sounding Hunt — Read the atmosphere. Find the location.**

WXspot (Weather Spot) is a game-first weather platform. Sounding Hunt is its first featured game, built around real radiosonde observations. Other weather-powered game modes and tools may follow; WXspot is the application brand, not Sounding Hunt. Each day, every player receives the same observed sounding and places one pin on a map of the contiguous United States. The server calculates the official WGS84 distance and score. Unlimited historical practice is unranked.

The Android client remains Kotlin, Jetpack Compose, Material 3, and MapLibre. The API remains the existing FastAPI modular monolith, and the PostgreSQL/PostGIS database and Railway API/worker remain in place. The new game domain is additive and documented in [Sounding Hunt architecture](docs/SOUNDING_HUNT_ARCHITECTURE.md).

## Product scope

The primary navigation is **Home | Play | Rankings | Profile**. The only game modes are Daily Challenge and Unlimited Practice. The old weather and community screens are no longer the app launch experience for this game-focused release. Radar, satellite, models and other weather data/render/provider capabilities remain in the backend and must not be decommissioned: they may support later WXspot gameplay. Existing backend routes, data, storage, signing lineage, and Railway services are retained for compatibility and rollback.

## Data source

Challenges use measured IGRA 2.2 radiosonde launches from NOAA/NCEI. The worker downloads a bounded station archive, validates actual pressure-level observations, preserves missing and QC-removed values as null, and publishes only validated, unused profiles. It does not synthesize observations. See [NOAA IGRA](https://www.ncei.noaa.gov/products/weather-balloon/integrated-global-radiosonde-archive).

## Visual direction and implementation

The existing branch UI has a working gameplay shell but still uses generic dark Material surfaces. The approved visual direction is an original, colorful, optimistic, low-poly-inspired weather-strategy game identity, with rigorous legibility and scientific fidelity in Skew-T and map surfaces. **This redesign is planned, not yet implemented.** See the [full source audit, design brief, and coding-agent implementation plan](docs/WXSPOT_GAME_VISUAL_REDESIGN_PLAN.md).

## Development

- Backend: `cd backend && pip install -e '.[test]' && pytest`
- Backend lint: `cd backend && ruff check wxspot tests && ruff format --check wxspot tests`
- Android: use the repository Gradle wrapper and the existing CI workflows. Keep `app.wxspot.beta`, its versioning, and signing configuration intact for beta updates.
- Local API and Railway deployment details: [Deployment and rollback](docs/DEPLOYMENT.md).

## Release status

Sounding Hunt is implemented on a dedicated draft pull request. Backend, Android, and API 30/36 emulator acceptance checks pass; CI has produced a review-only debug APK. Production Railway services and data have not been changed. Do not roll the branch into production until the visual redesign is implemented and tested; a staging challenge queue and migration are verified; physical Android behavior is checked; and the established beta signing key is available for an update-compatible release. See [current status](docs/PHASE2_STATUS.md).
