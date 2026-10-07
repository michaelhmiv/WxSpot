# Phase 2 implementation status

Updated: 2026-10-07

This file tracks verified work for the execution of `WxSpot_Phase2_Plan.md`. A task is complete only after its code, acceptance checks, and evidence are recorded.

## Current work

- Repository: `michaelhmiv/WxSpot`
- Main now contains P2-01 and P2-02 through merge commit `f881e562936c02718fa0d00c3e7ac98bfdfeef1a`.
- P2-01 PR #3 and P2-02 PR #4 are merged. P2-02 passed backend/PostGIS run 117, Android run 116, and live-device acceptance run 43 after fixing short protected archive-image reads.
- P2-03 is tracked in [PR #5 — Add bottom shell and saved places](https://github.com/michaelhmiv/WxSpot/pull/5), being refreshed onto the verified main base with the latest local implementation.
- The current P2-03 work includes bottom navigation, explicit Nominatim search through the backend, device-local places/camera/units, foreground GPS, and a geographic NOAA radar-station picker. CI and device acceptance remain pending.
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
| P2-02 — Radar reliability | Complete | Separates requested/displayed frames and generation-aware readiness; keeps the prior frame visible; bounds prefetch, requests, and tile cache; gates playback on successful display and pauses when inactive. Candidate tile parsing must be followed by a renderer frame; request-cache probes do not hold readiness. Backend/PostGIS run 117, Android run 116, and live-device run 43 all pass. The replay run verifies archive loading, a real device-dispatched pan, and ten warmed playback advances. A regression test covers short, exact-limit, and oversized archive bodies. |
| P2-03 — Bottom shell and places | In progress | Material 3 bottom navigation and controls, neutral-point selection, explicit Nominatim search with attribution and a database-backed cross-replica rate gate, local saved-place CRUD/reordering, last camera and units, foreground coarse/fine GPS, and nearby NOAA NEXRAD station selection are implemented in the current worktree. Backend fixtures and real-provider device tests are added. Formatter preview and P2-03 CI/device acceptance are pending; verify live search/station responses, permission denial, persistence, and bottom-shell integration before marking complete. |
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

Finish formatting and publishing the refreshed P2-03 change on the verified main base; run its backend, Android, and live-device acceptance checks. Then continue through P2-04–P2-10 in the dependency order in the implementation plan; do not mark a task complete from a scaffold or a unit fixture alone.
