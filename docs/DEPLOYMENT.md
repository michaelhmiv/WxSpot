# Deployment and rollback

## Current topology

Railway retains the existing FastAPI API service, one weather worker, PostgreSQL/PostGIS, and the existing S3-compatible media storage. This implementation adds no permanent service and does not change Railway production variables, domains, database, worker count, or storage. The Android beta application ID and release signing lineage remain unchanged.

## Safe rollout sequence

1. Keep the pull request draft until backend, Android, and API 30/36 emulator CI pass and staging plus physical-device gates are ready. CI passed on commit `44aa8dd`; staging and physical-device verification remain open.
2. Deploy the branch API and worker to staging through the existing Railway pipeline. The API migration runs through the existing predeploy migration step; revision `0006` only creates game tables and indexes.
3. Confirm API health, migration head, and worker logs. Allow bounded IGRA ingestion to build a verified candidate pool and a 14-day queue. Use `/game/sounding-hunt/admin/status` and `/game/sounding-hunt/admin/candidates` with a moderator account.
4. Verify the active `/game/sounding-hunt/today` response contains no station identity or coordinates, complete a test ranked submission with a test account, verify result/leaderboard/profile, and verify resubmission returns 409. Exercise rollover and source-outage fallback.
5. Build the Android beta with the established key and package identity. Install/update on a physical Android device, verify guest persistence, chart touch interaction, map placement, result, leaderboard, offline/error handling, and process restart.
6. Merge and roll out the new Android client only after staging and physical checks pass. Keep legacy data, routes, storage, services, and additive tables during the rollback window.

There is no verified staging deployment in this change. Do not use the production database as a test fixture and do not publish a release artifact without the existing signing key.

## Rollback

Redeploy the previous Git revision and restore the previous Android beta package build if necessary. Leave revision `0006` tables and all legacy data untouched. Do not downgrade the migration, drop the Railway worker/API/database/storage service, or delete source artifacts as part of application rollback.

## Worker behavior and operating cost

The existing worker checks the queue every 15 minutes. It publishes from verified unused profiles before attempting more ingestion; each ingestion batch is capped at three station archives, with at most two batches (six archives total) per maintenance pass. Each archive is bounded to 16 MiB. Each parsed archive retains up to 32 real launches; queue publication reserves at least four unassigned profiles for practice when the candidate pool permits. The existing single worker/process avoids overlapping selection jobs. It emits low-pool warnings and continues serving already-published challenges during NOAA outages. No request-time NOAA dependency exists.

## Release blocker checklist

- Backend, Android, and API 30/36 emulator CI passed on commit `44aa8dd`; links are recorded in [current status](PHASE2_STATUS.md).
- The verified pool and current challenge must exist before app rollout.
- Railway predeploy migration must be reviewed against the current production schema.
- Existing beta keystore and credentials are needed to produce a compatible signed APK.
- A physical Android device and staging environment are needed to verify update, chart/map interaction, rollout queue, rollover, and source-outage behavior.
