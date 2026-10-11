# API overview

The existing FastAPI service remains the only backend. Legacy weather and account APIs are retained during migration. Sounding Hunt is isolated under `/game/sounding-hunt` and uses versioned Pydantic response models rather than serializing ORM entities.

## Player routes

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/game/sounding-hunt/today` | Current active challenge, sanitized profile, completion state, streak |
| `GET` | `/game/sounding-hunt/daily/{challenge_day}` | Sanitized released profile for chart review; upcoming profiles return 404 |
| `POST` | `/game/sounding-hunt/daily/{challenge_day}/guess` | Final official guess; returns authorized reveal, distance, score |
| `GET` | `/game/sounding-hunt/daily/{challenge_day}/result` | Own authorized result or a closed historical reveal |
| `GET` | `/game/sounding-hunt/leaderboard/{challenge_day}?page=1` | Paginated ranked rows and the caller's rank; never precise guess coordinates |
| `GET` | `/game/sounding-hunt/profile` | Server-computed daily stats, streaks, and result history |
| `POST` | `/game/sounding-hunt/practice` | Creates an unranked session from an eligible observation |
| `POST` | `/game/sounding-hunt/practice/{practice_id}/guess` | Final practice guess and reveal |
| `GET` | `/game/sounding-hunt/practice/{practice_id}/result` | Own completed practice result |

Daily and practice guess bodies contain `latitude` and `longitude`. The service rejects nonfinite and out-of-range coordinates. Score and distance are calculated only on the server with WGS84 geodesics.

Public chart responses include `observation_time` in UTC and an `observation_time_basis` of `launch` or `nominal`. When IGRA does not provide a release time, the chart labels the available nominal observation time instead of presenting it as a measured launch time.

## Operations routes

`GET /game/sounding-hunt/admin/status` and `GET /game/sounding-hunt/admin/candidates` report queue health and validation. `PATCH /game/sounding-hunt/admin/observations/{identity}` excludes or restores a candidate. These routes require moderator or superuser authorization.

All game routes require a valid existing guest/session bearer token. Request size limits, HTTPS deployment, auth renewal, and per-player quotas reuse current infrastructure.
