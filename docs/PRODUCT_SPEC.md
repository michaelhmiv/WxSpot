# Product specification: WXspot flagship game — Sounding Hunt

## Purpose

**WXspot (Weather Spot) is the Android application and weather-game platform. Sounding Hunt is its first flagship game, not the product's new name.** The present release can be game-first rather than a general weather-analysis dashboard. The Sounding Hunt launch experience is the shared Daily Sounding Hunt; unlimited practice uses verified historical observations without affecting rankings or streaks. The existing radar, satellite, model and weather infrastructure must remain available for future WXspot games and utilities.

## Player loop

1. Home presents the current daily challenge, completion status, streak, recent result, and one-tap play.
2. The player sees the observation date and UTC time before guessing. The chart labels a source release time as a launch time and clearly labels the nominal time when IGRA has no release time. A native Skew-T/log-P chart shows observed temperature, dew point, pressure, and available winds. Touch inspection and reset are available.
3. The player taps/repositions a pin on a lower-48 map or enters signed decimal coordinates, then explicitly confirms the final guess.
4. The server persists the one ranked attempt and returns the reveal, geodesic distance, 0–5,000 score, and concise evidence-based interpretation.
5. The player can review the chart, open the daily board, share a spoiler-free score, play practice, or return Home.

There is no countdown, forced registration, advertising, or social feed.

## Daily rules

- Calendar identity is the Eastern date whose active window starts at 08:00 America/New_York. The window is computed with IANA timezone rules, so it can be 23, 24, or 25 hours.
- The API serves one prepublished challenge to all players. Its hand-built public DTO exposes observed UTC time, whether that time is a release or nominal observation time, surface pressure, and profile levels. Station names, IDs, coordinates, elevation, source metadata, and results stay private until an authorized reveal.
- One official attempt per account and challenge is enforced by a database unique constraint. A missed challenge breaks the active streak. Anonymous profiles can be recreated; the game does not claim one-person anti-cheat.
- The initial persisted score configuration is `round(5000 × exp(-distanceMiles / 750))`, clamped to 0–5000, using a WGS84 geodesic. A challenge stores its scoring version and scale.
- Rankings sort by score descending, distance ascending, submission time ascending, then stable user ID. Precise guesses are never listed.

## Sounding and answer quality

The source is NOAA/NCEI IGRA 2.2 observed launches. Candidates must be within the contiguous U.S., have at least 12 usable levels, at least 10 measured temperatures, at least 6 measured dew points, and reach 500 hPa. Pressure, coordinate, timestamp, and profile ordering checks apply. Missing/QC-removed data remains missing. Winds and standard launch times improve selection quality but are not fabricated when unavailable.

The worker maintains up to 14 upcoming daily publications from validated, unused observations. It avoids a station used in the prior 30 days when alternatives are available and varies broad region, launch cycle, and profile quality. It also compares measured thermodynamic layers against recently published profiles and prefers a less similar candidate when data quality is comparable. If a candidate is unsuitable, the worker records why and tries another verified candidate; it never invents one.

## Navigation and visual system

The current **Sounding Hunt-focused WXspot shell** has four bottom-navigation destinations: Home, Play, Rankings, and Profile. Active chart and map steps use an immersive layout. The existing Skew-T and MapLibre foundations are reused and must stay scientifically/geographically accurate. The redesigned UI should feel like an original, uplifting miniature weather-strategy world rather than a dark instrumentation dashboard. The result reveals station metadata, both locations, a connecting line, distance, score, observation time, provenance, and two to four concise deterministic insights. The full source audit, component design system, screen-level requirements, tests and rollout plan are in [WXspot game visual redesign plan](WXSPOT_GAME_VISUAL_REDESIGN_PLAN.md). **Visual redesign work remains pending implementation.**

## Explicit exclusions

Separate radar/forecast/satellite **game modes**, social/community features, chat, head-to-head play, paid content, ads, and standalone weather-utility **screens** are outside this release. This exclusion does **not** authorize removing existing radar, satellite, forecast/model, rendering, sounding, weather-data, or worker capabilities. Optional historically valid weather context may be introduced post-reveal if it does not disclose answers before guessing or increase complexity/cost; it is not a launch blocker.
