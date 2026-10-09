# Data model

Revision `0006_sounding_hunt` is additive to the existing schema.

| Table | Purpose | Retention and constraints |
|---|---|---|
| `sounding_hunt_stations` | Private IGRA station identity, official name/state, verified location/elevation, source version | One row per station; retained for provenance |
| `sounding_hunt_observations` | Parsed observed profile, validation report, revision hash, ingestion time, eligibility/exclusion | Unique station + observed time; candidate identity primary key |
| `sounding_hunt_ingestion_status` | Last attempt, accepted/rejected/failed status and reason per station | Bounded to station inventory |
| `sounding_hunt_daily_challenges` | Eastern challenge date/window, unique observation, number, score version/scale | One challenge per day; one use per observation |
| `sounding_hunt_daily_guesses` | Official player coordinates, calculated distance/score, version, submission time | Unique player + challenge; indexed board ordering |
| `sounding_hunt_practice` | Unranked session, selected observation, submitted guess and score configuration | Indexed by player/time; no leaderboard or streak effects |

UTC timestamps are stored internally. `challenge_day` is the calendar identity for the 08:00 America/New_York reset. Source station coordinates and identifiers remain private in station/observation rows until reveal.

Production rollback is application rollback with the additive tables retained. The migration downgrade drops game tables and must not be used after real player results have been recorded.
