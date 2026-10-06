# WxSpot

Android-first weather learning through geographic annotations and exact weather-context replay.

- Kotlin, Jetpack Compose, Material 3, MapLibre Native.
- FastAPI, PostgreSQL/PostGIS, S3-compatible media storage.
- NOAA RIDGE2 reflectivity/velocity and official NWS alerts.
- Anonymous map browsing; authenticated community actions.

Start with [product](docs/PRODUCT_SPEC.md), [architecture](docs/ARCHITECTURE.md),
[data sources](docs/WEATHER_DATA_SOURCES.md), [data model](docs/DATA_MODEL.md),
[deployment](docs/DEPLOYMENT.md), and [verification / Phase 2](docs/ACCEPTANCE.md).

Local backend: `docker compose -f infra/compose.yaml up --build`.
API documentation: http://localhost:8000/docs.

Backend checks: `pip install -e 'backend[test]'`, then from backend run
`ruff check .`, `ruff format --check .`, and `pytest` with a real PostGIS database.

Open `android` in Android Studio. API base URL is a Gradle property; production builds
use the deployed Railway endpoint and development may use the emulator's 10.0.2.2.
See deployment and acceptance documents for supported behavior and release gates.
