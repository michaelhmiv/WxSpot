# Phase 2 beta verification

Updated October 8, 2026. P2-01 through P2-09 are complete. P2-10 software acceptance passed; physical Pixel 8 Pro checks remain open. [PR #11](https://github.com/michaelhmiv/WxSpot/pull/11) is merged at `73a2d341ed43a481aeaa51d39a29ae444a45e059`. The authoritative scope is `WxSpot_Phase2_Plan.md`.

## Accepted software

The signed candidate is **WxSpot Beta 0.2.0-beta.2**, version code **4**, package `app.wxspot.beta`. It uses the production HTTPS API, enables code/resource optimization and disables cleartext traffic. Candidate source: `11e52a338ac4bb66ddd69c4df5419275100bcee2`. Final documentation and future-build defaults may be newer than the APK's source commit.

| Gate | Result |
| --- | --- |
| [Backend/PostGIS/live sources](https://github.com/michaelhmiv/WxSpot/actions/runs/37842655896) | Formatting/lint, 96 deterministic/integration tests and five live-source suites passed. |
| [Android checks](https://github.com/michaelhmiv/WxSpot/actions/runs/37842656017) | Formatting, unit tests, instrumentation compilation, lint, debug build and optimized release build passed. |
| [Native API 30/36 matrix](https://github.com/michaelhmiv/WxSpot/actions/runs/37842655997) | Both API jobs passed. An API 36 setup attempt had a corrupted SDK image download before tests; the successful retry is the accepted result. |
| Production | API deployment `8ae567da-e5d4-4319-9e39-397650924a84` and worker deployment `5198f2cb-c1c4-4dfa-9b50-8e2250351eee` are successful at the merged code; all replicas online, no pending work or service issues. |

| Emulator | Native tests / failures | Same-signer upgrade | Model archive pixel proof |
| --- | --- | --- | --- |
| API 30 | 12 / 0 | 3 → 4, passed | HRRR 49/49; GFS 45/49 |
| API 36 | 12 / 0 | 3 → 4, passed | HRRR 49/49; GFS 45/49 |

Each device job also passes a separate version 3 seed test and a platform-only optimized version 4 verification. The upgrade checks actual package version/certificate, AES-GCM-encrypted profile and resume credential, draft bytes, places, camera and units. It resumes the draft editor, opens saved places and renews the original identity against the real production endpoint. It uses APK replacement without uninstalling or clearing app data.

The twelve native cases cover GPS denial/manual search, source controls, saved-place persistence, real radar/MRMS rainfall/GOES/HRRR/GFS capture and replay, independent profiles, block/deletion access, playback and returning to the marked view, network loss/recovery, lifecycle, forecast/observed soundings and NWS location weather. Native model snapshots are compared with geographic pixels from the preserved archive; screenshots follow successful raster drawing, rather than Compose idleness alone.

The five-source PostGIS audit verifies original context, source expiry, live-cache cleanup, authorized viewers, blocks/deletion, failed captures without partial posts and legacy v1 decoding. Protected archive responses are `private, no-store`, vary by authorization and use uncached Android requests. Location-refresh failures retain cached source intervals and report them stale. A same-scan network recovery is accepted only for matching selection and viewport generations.

## Signing and update continuity

APK SHA-256: `82977a6e294ab30829a9f95eb87f96c650a35395b4fadc66e1fbe362efc9ad21`

Canonical beta certificate SHA-256: `eac9f28b805bd65ce7dea71c7aaaa1736a53dcb22864a66841ad008e48e775b5`. The public certificate is in `BETA_SIGNING_CERTIFICATE.pem`; the matching private keystore and build configuration are retained privately. Local APK signature verification passes using APK Signature Scheme v2 with one RSA 3072-bit signer.

The original `WxSpot-0.1.1-debug.apk` certificate is `8ee180e0c49e7f7ebb3ffc1dc6776bcaac516660f40410aa7bab548c9b1d731a`; its private signing key was not found. Install **WxSpot Beta** beside the original app. Keep the original installation to preserve its local profile, places and drafts. The first beta installation has its own local data and automatic device identity. Subsequent beta updates must use the canonical beta signer and version code 5 or greater.

Acceptance-job signing material is encrypted with AES-256-CBC and RSA-OAEP before CI upload, then recovered and checked against the APK certificate privately. No private signer/password belongs in Git or plain CI evidence. The manual beta workflow validates this public certificate and requires `WXSPOT_KEYSTORE_BASE64`, `WXSPOT_KEYSTORE_PASSWORD`, `WXSPOT_KEY_ALIAS` and `WXSPOT_KEY_PASSWORD` repository secrets. This connection cannot configure those secrets; the retained signer also supports local builds through the documented four environment variables.

## Emulator measurements and physical checks

These are debug emulator renderer-readiness events from the accepted jobs, including several sources and archives. They are not cold-launch, end-to-end network, optimized-release or physical Pixel measurements.

| Scope | Ready events | Median ms | P95 ms | Max ms | Peak PSS KB |
| --- | --- | --- | --- | --- | --- |
| API 30 emulator | 63 | 707 | 1700 | 2290 | 632674 |
| API 36 emulator | 69 | 1157 | 3130 | 3749 | 450403 |

Physical Pixel 8 Pro cold/warm targets, controlled 10 Mbps / 100 ms loading, gesture smoothness, memory and battery remain unmeasured. Do not mark those checks complete from emulator results.

## Commands

Backend: `ruff check .`, `ruff format --check .`, CI PostGIS migrations, deterministic `pytest` and the five live-source suites in `backend.yml`.

Android: `:app:spotlessCheck :app:testDebugUnitTest :app:compileDebugAndroidTestKotlin :app:lintDebug :app:assembleDebug :app:assembleRelease`. Each device job runs `.github/scripts/upgrade.sh` first, followed by `.github/scripts/device.sh`. Release instrumentation uses `-Pwxspot.testBuildType=release` and the platform-only upgrade driver, preserving normal production optimization.
