# Phase 2 implementation status

Updated: 2026-10-07

This file tracks verified work for the execution of `WxSpot_Phase2_Plan.md`. A task is complete only after its code, acceptance checks, and evidence are recorded.

## Current work

- Repository: `michaelhmiv/WxSpot`
- Main contains P2-01 through P2-03 at `d7d177c485f9c36df6b96b982ed1b01b970edbb9`.
- P2-01 PR #3 and P2-02 PR #4 are merged. P2-02 passed backend/PostGIS run 117, Android run 116, and live-device acceptance run 43 after fixing short protected archive-image reads.
- P2-03 [PR #5 — Add bottom shell and saved places](https://github.com/michaelhmiv/WxSpot/pull/5) is merged. It passed [backend run](https://github.com/michaelhmiv/WxSpot/actions/runs/37671472962), [Android run](https://github.com/michaelhmiv/WxSpot/actions/runs/37671472950), and [live-device run](https://github.com/michaelhmiv/WxSpot/actions/runs/37671472928); the device flow verifies saved places, search/station results, permission handling, and persistence.
- P2-03 is deployed to Railway production; API deployment `e3efd181-28e5-4032-a528-8b7215e272bc` completed successfully.
- P2-04 expanded-radar work is being resumed on `p2/p2-04-expanded-radar`; the implementation is not yet merged or deployed.
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
| P2-02 — Radar reliability | Complete | Separates requested/displayed frames and generation-aware readiness; keeps the prior frame visible; bounds prefetch, requests, and tile cache; gates playback on successful display and pauses when inactive. Candidate tile parsing must be followed by a renderer frame; request-cache probes do not hold readiness. Backend/PostGIS run 117, Android run 116, and live-device run 43 all pass. The replay run verifies archive loading, a real device-dispatched pan, and ten warmed playback advances. A regression test covers short, exact-limit, and oversized archive bodies. |
| P2-03 — Bottom shell and places | Complete | PR #5 merged and deployed. The Android/device workflow passed for the integrated shell, explicit Nominatim search, local saved-place persistence, foreground location and nearby radar-site selection. Backend, Android and live-device run evidence is linked above. |
| P2-04 — National and expanded radar | In progress | Candidate branch adds five MRMS GRIB2 products, six NEXRAD Level III products, missing/range-fold masks, actual header elevation and range-bin spacing, exact capture, render/legend endpoints, and product selection. Six Level III fixtures and a five-product live MRMS smoke test are included. Python syntax compilation passed. Local pytest/ruff and Android Gradle checks cannot run here because their packages and Gradle distribution are unavailable; hosted backend, Android and live-device acceptance are pending. No merge or deployment has been claimed. |
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

Finish P2-04 on the verified main base and record its hosted backend, Android and live-device evidence. Then continue P2-05 through P2-10 in the dependency order in the implementation plan; do not mark a task complete from a scaffold or a unit fixture alone.
