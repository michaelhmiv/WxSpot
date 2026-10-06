# Phase 2 implementation status

Updated: 2026-10-06

This file tracks verified work for the execution of `WxSpot_Phase2_Plan.md`. A task is complete only after its code, acceptance checks, and evidence are recorded.

## Current work

- Repository: `michaelhmiv/WxSpot`
- Starting `main` commit: `f54aea7dcca173933d2eddb4d0c03c442df52df2`
- Working branch: `p2/p2-02-radar-reliability` (stacked on `p2/p2-01-weather-contracts`)
- Current PR: [#3 — P2-01: Add shared weather frame contracts](https://github.com/michaelhmiv/WxSpot/pull/3), draft; all acceptance workflows pass. P2-02 is ready for its own stacked draft PR.
- Production Railway: unchanged during this work
- Signing continuity: no stable signing key is configured in the repository; the original review APK signing key has not been verified.

## Baseline discovery

- No `AGENTS.md` was present in the checkout.
- Phase 1 contains the no-sign-in Android flow, device profile, two RIDGE2 products, exact radar capture, PostGIS social records, and CI workflows.
- The repository has no local PostGIS service in this execution container. Docker and ADB are unavailable; use GitHub CI's PostGIS service and Android emulator, and report Pixel 8 Pro checks separately.
- Backend baseline before edits: `ruff check .` and `ruff format --check .` passed; `pytest -q tests/test_providers.py tests/test_domain.py` passed (20 tests).
- Android local baseline: `GRADLE_USER_HOME=/tmp/wxspot-gradle ./gradlew :app:spotlessCheck :app:testDebugUnitTest --no-daemon` could not start because no Android SDK is installed. Java 17 and Gradle 9.6.0 are present.

## Task state

| Task | State | Evidence / remaining work |
| --- | --- | --- |
| P2-01 — Weather contracts and state | Complete | Added source-neutral backend contracts, registry and RIDGE2 adapter, generic catalog/frame endpoints, Kotlin wire models/API calls, and a shared response fixture. Local `ruff check .`, `ruff format --check .`, and `pytest -q tests/test_providers.py tests/test_weather_contracts.py tests/test_domain.py` pass (25 tests). A real NOAA KCLX reflectivity inventory returned 22 timestamped frames with dBZ units. Backend/PostGIS run [34](https://github.com/michaelhmiv/WxSpot/actions/runs/37549022800), Android run [33](https://github.com/michaelhmiv/WxSpot/actions/runs/37549022603), and live-device run [14](https://github.com/michaelhmiv/WxSpot/actions/runs/37549022623) all pass. Existing radar/post replay regressions and shared contract fixtures passed. |
| P2-02 — Radar reliability | In progress | Separates requested/displayed frames and generation-aware readiness; keeps the prior frame visible; bounds prefetch, requests, and tile cache; gates playback on successful display and pauses when inactive. Unit and ten-advance live playback checks are added. Android/device execution and renderer behavior remain under CI verification. |
| P2-03 — Bottom shell and places | Not started | Bottom-only navigation, foreground GPS, real search, saved places, and nearby station selection remain. |
| P2-04 — National and expanded radar | Not started | MRMS, Level III decode, physical units/masks, storm-relative velocity, product tilts, precipitation and exact capture remain. |
| P2-05 — Satellite | Not started | Validated GOES products, projection, controls, replay/capture remain. |
| P2-06 — HRRR/GFS maps | Not started | Bounded GRIB ingestion, real field/run catalogs, render/cache and model capture remain. |
| P2-07 — Full interactive soundings | Not started | Forecast/observed profiles, interactive charts, and independently reviewed calculations remain. |
| P2-08 — Location weather | Not started | NWS observations/forecasts, saved place panel, partial/stale source states remain. |
| P2-09 — Complete community replay | Not started | Cross-source archive/access/replay acceptance remains. |
| P2-10 — Beta integration | Not started | Full device matrix, signing continuity/migration, review APK and release evidence remain. |

## Decisions and source limits

- Keep v1 `WeatherContext`, `WeatherLayer` wire names, radar post decoding, and `/weather/radar/frames` unchanged.
- Generic frame identity prefixes source type and provider and retains exact product/site/time identity. Unknown coverage remains null. A common fixture is parsed by backend tests and Android repository tests.
- Only the current RIDGE2 adapter is in the catalog. Its velocity remains labeled “provider scale”; it is not converted to m/s from rendered pixels.
- Every provider request and exact publication capture is dispatched from a registered `(source_type, provider)` pair. Client-supplied URLs are not used for captures.
- Merges and production deployment will be considered after implementation, review evidence, and the final release checks. Do not report a deployment until Railway confirms it.

## Next action

Publish P2-02 as a focused stacked draft PR and address its build, test, and renderer findings before taking up P2-03.
