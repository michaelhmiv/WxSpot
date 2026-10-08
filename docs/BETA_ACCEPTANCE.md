# Phase 2 beta verification

Updated October 8, 2026. P2-01 through P2-08 are merged; P2-09/P2-10 acceptance is in progress. The authoritative scope is `WxSpot_Phase2_Plan.md`.

## Acceptance coverage

| Check | Evidence and scope |
| --- | --- |
| Source parsing, calculations, contracts | Backend CI runs deterministic fixtures and PostGIS tests, then live MRMS, GOES, HRRR/GFS, soundings and NWS location checks. Location PR #10 passed run 37775051825. Local 15 source/calculation checks and lint/format pass. |
| Native Android UI | API 30 and API 36 matrix uses real source data with a local test API/PostGIS/worker. Covers bottom navigation, GPS denial, search/places, annotations, independent profiles, access rules, ten warmed radar advances, rapid source switches, satellite/model capture and exact replay, interactive soundings and location weather. Full beta matrix is pending. |
| Cross-source archive retention | Five-source boundary audit verifies original camera/vectors/frame identity, independent viewers, blocked/deleted access, source expiry, live-cache cleanup, capture failure without partial posts, and legacy v1 radar decoding. Private archive responses are `private, no-store` and vary by authorization. Real rainfall capture/replay is added to the device flow; hosted result pending. |
| Airplane mode and recovery | Device test disables network, verifies no active network, refreshes, retains the displayed frame and original time/profile, then restores networking and verifies readiness. A same-scan refresh restores its existing successful render only when selection and viewport generations match. Separate location refresh unit test retains source intervals and marks successful cached sections stale until recovery. |
| Lifecycle | Backgrounding stops playback; resume restores requested/displayed frame agreement without restarting animation. |
| Same-key APK update | Device acceptance creates an explicit signer, installs beta version 3, seeds encrypted profile/resume credential, draft, places, camera and units, then replaces the APK with optimized version 4. A release-targeted instrumentation APK applies the release mapping. Verify checks package version/certificate, persisted values, restored draft UI and real credential renewal. No uninstall or app-data clearing occurs between versions. Hosted result pending. |
| Release candidate | Version 4 / `0.2.0-beta.2`, package `app.wxspot.beta`, production HTTPS API, resource/code optimization enabled and cleartext disabled. A successful candidate and signer will be retained after the matrix passes. |
| Physical Pixel 8 Pro | Unmeasured: cold/warm latency targets, controlled 10 Mbps/100 ms loading and physical gesture/memory performance. Emulator traces must not be reported as Pixel measurements. |

## Signing transition and custody

The original `WxSpot-0.1.1-debug.apk` certificate SHA-256 is `8ee180e0c49e7f7ebb3ffc1dc6776bcaac516660f40410aa7bab548c9b1d731a`; its private signing key was not found. The beta uses the separate application ID `app.wxspot.beta` and label **WxSpot Beta**, allowing installation beside the original review app. The original app's local profile, places and drafts remain in its installation. The first beta installation has its own profile and places; it cannot inherit another package's encrypted credentials. Do not uninstall the original to install beta. Subsequent beta updates require the retained beta signer and increasing version codes.

The acceptance job's private signing key/passwords are encrypted together with AES-256-CBC and RSA-OAEP to `BETA_RECOVERY_RECIPIENT.pem` before any artifact upload. The corresponding private recovery key is kept outside Git. Only a passing candidate can become the release lineage. Its decrypted keystore/configuration must be retained privately; the public beta certificate is recorded in `BETA_SIGNING_CERTIFICATE.pem`. No private signing material belongs in repository files or plain CI artifacts.

`.github/workflows/beta.yml` supports future signed builds using `WXSPOT_KEYSTORE_BASE64`, `WXSPOT_KEYSTORE_PASSWORD`, `WXSPOT_KEY_ALIAS`, and `WXSPOT_KEY_PASSWORD` repository secrets. It rejects missing variables and a certificate mismatch. Setting GitHub secrets is not available through this connection; the same retained key can be used for local builds via `WXSPOT_KEYSTORE_PATH` and the remaining three environment variables. Do not generate a replacement signing key for future betas.

## Commands

Backend: `ruff check .`, `ruff format --check .`, migrations against CI PostGIS, deterministic `pytest` followed by the five documented live-source suites in `backend.yml`.

Android: `:app:spotlessCheck :app:testDebugUnitTest :app:compileDebugAndroidTestKotlin :app:lintDebug :app:assembleDebug :app:assembleRelease`. Device: `.github/scripts/device.sh`, then `.github/scripts/upgrade.sh`. Release instrumentation uses `-Pwxspot.testBuildType=release`.

Do not claim a task complete from an APK build alone. Record exact CI runs, deployment commits, candidate certificate and checksum after acceptance succeeds.
