# Phase 2 implementation status

Updated: 2026-10-08

This file tracks verified work for the execution of `WxSpot_Phase2_Plan.md`. A task is complete only after its code, acceptance checks, and evidence are recorded.

## Current work

- Repository: `michaelhmiv/WxSpot`
- Main contains P2-01 through P2-06 at `0f8ccae1940ecbb808c9c82aaebacd1e1a2acc7b`.
- P2-01 PR #3 and P2-02 PR #4 are merged. P2-02 passed backend/PostGIS run 117, Android run 116, and live-device acceptance run 43 after fixing short protected archive-image reads.
- P2-03 [PR #5 — Add bottom shell and saved places](https://github.com/michaelhmiv/WxSpot/pull/5) is merged. It passed [backend run](https://github.com/michaelhmiv/WxSpot/actions/runs/37671472962), [Android run](https://github.com/michaelhmiv/WxSpot/actions/runs/37671472950), and [live-device run](https://github.com/michaelhmiv/WxSpot/actions/runs/37671472928); the device flow verifies saved places, search/station results, permission handling, and persistence.
- P2-03 is deployed to Railway production; API deployment `e3efd181-28e5-4032-a528-8b7215e272bc` completed successfully.
- P2-04 [PR #6](https://github.com/michaelhmiv/WxSpot/pull/6) is merged. Backend/PostGIS/live MRMS [run 176](https://github.com/michaelhmiv/WxSpot/actions/runs/37703346104), Android [run 175](https://github.com/michaelhmiv/WxSpot/actions/runs/37703345948), and live-device [run 70](https://github.com/michaelhmiv/WxSpot/actions/runs/37703345998) all passed at head `46738d8`. Railway deployment `ea33d925-a658-4b58-98ae-66bedc03b93c` is successful and online.
- P2-05 [PR #7](https://github.com/michaelhmiv/WxSpot/pull/7) is merged. Backend run 182, Android run 181, and live-data emulator run 72 (attempt 2) passed at `85a6429`. Railway API deployment `f84c0f90-10bb-4639-aa8e-613a7eba3f64` and new weather-worker deployment `311fab85-5e52-471c-873c-ac2aec0476aa` are successful and online. Worker service `afa4d75d-26d9-4de1-9996-3e54f629f12e` has one replica, 1 GB memory and 1 vCPU, and shares database/media references with the API.
- P2-06 [PR #8](https://github.com/michaelhmiv/WxSpot/pull/8) is merged. [Backend/PostGIS and live-model checks](https://github.com/michaelhmiv/WxSpot/actions/runs/37768728832), [Android checks and APK](https://github.com/michaelhmiv/WxSpot/actions/runs/37768728836), and [live emulator capture/replay](https://github.com/michaelhmiv/WxSpot/actions/runs/37768728897) pass at `12e2410`. The emulator covers both model identities, annotation capture, independent archive opening, timeline advancement and returning to the saved frame. Pin taps and held presses now have distinct actions. Railway API deployment `84852b56-b7c8-4f2b-8c89-fec047c4fc23` and worker deployment `4d6dae43-f4c9-40fc-b611-7a82dd7d0a47` are successful and online, with no pending work or failures.
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
| P2-04 — National and expanded radar | Complete | Five MRMS products and six Level III products preserve units, masks, actual header elevation and capture identity. All hosted gates passed; merged and production deployment verified above. |
| P2-05 — Satellite | Complete | Dynamically discovers operational East/West IDs; implements GeoColor, C02, C13 and C08/C09/C10 with native ABI projection, actual scan times, DQF masking, units/legends and bottom controls. All twelve real sector/product combinations passed after row-chunk optimization (observed peak RSS 415,432 KB). Native NOAA cutouts verify independent projection/temperature references. Shared worker queue, leases, upload ledger, finite retries, live-only cleanup and client preparation gates are included. Hosted backend, Android and real-source emulator channel/capture/block/replay checks passed. Merged and API/worker deployment verified above; physical Pixel performance remains a P2-10 check. |
| P2-06 — HRRR/GFS maps | Complete | All twenty real fields plus long available run totals pass. Hosted backend, Android and HRRR/GFS capture/replay checks pass; PR #8 is merged and API/worker deployment verified above. |
| P2-07 — Full interactive soundings | In progress | Forecast columns and IGRA launches, separate shared profile/diagnostic jobs, bounded raw-field reuse, MetPy reference diagnostics, native Skew-T/hodograph charts and bottom parcel/motion/time controls are implemented. Seven local reference/QC/geometry tests pass. Live HRRR extraction returned 40 levels in 34.37 s (138,305,213 input bytes, 201 exact ranges); GFS returned 24 levels in 12.44 s (22,675 bytes, one subset). Charleston IGRA release time and QC parsing are verified. Hosted PostGIS/Android/native-gesture gates are pending; do not mark complete yet. |
| P2-08 — Location weather | Not started | NWS observations/forecasts, saved place panel, partial/stale source states remain. |
| P2-09 — Complete community replay | Not started | Cross-source archive/access/replay acceptance remains. |
| P2-10 — Beta integration | Not started | Full device matrix, signing continuity/migration, review APK and release evidence remain. |

## Decisions and source limits

- Keep v1 `WeatherContext`, `WeatherLayer` wire names, radar post decoding, and `/weather/radar/frames` unchanged.
- Generic frame identity prefixes source type and provider and retains exact product/site/time identity. Unknown coverage remains null. A common fixture is parsed by backend tests and Android repository tests.
- The catalog now includes the RIDGE2 compatibility adapter, MRMS and NEXRAD Level III candidates. Its velocity remains labeled “provider scale”; it is not converted to m/s from rendered pixels.
- Every provider request and exact publication capture is dispatched from a registered `(source_type, provider)` pair. Client-supplied URLs are not used for captures.
- Merges and production deployment will be considered after implementation, review evidence, and the final release checks. Do not report a deployment until Railway confirms it.

## Next action

Verify the integrated sounding worker/API and native gesture flow, then implement location observations and forecasts. Continue P2-06 through P2-10 in the dependency order in the implementation plan; do not mark a task complete from a scaffold or a unit fixture alone.
