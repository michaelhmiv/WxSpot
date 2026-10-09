# Product specification: Sounding Hunt

## Purpose

WXspot is a focused Android game about reading the atmosphere and locating a real radiosonde launch. It is not a general weather application. Its launch experience is the shared Daily Sounding Hunt; unlimited practice uses verified historical observations without affecting rankings or streaks.

## Player loop

1. Home presents the current daily challenge, completion status, streak, recent result, and one-tap play.
2. The player sees the observation date and UTC launch time before guessing. A native Skew-T/log-P chart shows observed temperature, dew point, pressure, and available winds. Touch inspection and reset are available.
3. The player taps/repositions a pin on a lower-48 map or enters signed decimal coordinates, then explicitly confirms the final guess.
4. The server persists the one ranked attempt and returns the reveal, geodesic distance, 0–5,000 score, and concise evidence-based interpretation.
5. The player can review the chart, open the daily board, share a spoiler-free score, play practice, or return Home.

There is no countdown, forced registration, advertising, or social feed.

## Daily rules

- Calendar identity is the Eastern date whose active window starts at 08:00 America/New_York. The window is computed with IANA timezone rules, so it can be 23, 24, or 25 hours.
- The API serves one prepublished challenge to all players. It exposes a hand-built public DTO with observed time and profile levels only. Station names, IDs, coordinates, elevation, source metadata, and results stay private until an authorized reveal.
- One official attempt per account and challenge is enforced by a database unique constraint. A missed challenge breaks the active streak. Anonymous profiles can be recreated; the game does not claim one-person anti-cheat.
- The initial persisted score configuration is `round(5000 × exp(-distanceMiles / 750))`, clamped to 0–5000, using a WGS84 geodesic. A challenge stores its scoring version and scale.
- Rankings sort by score descending, distance ascending, submission time ascending, then stable user ID. Precise guesses are never listed.

## Sounding and answer quality

The source is NOAA/NCEI IGRA 2.2 observed launches. Candidates must be within the contiguous U.S., have at least 12 usable levels, at least 10 measured temperatures, at least 6 measured dew points, and reach 500 hPa. Pressure, coordinate, timestamp, and profile ordering checks apply. Missing/QC-removed data remains missing. Winds and standard launch times improve selection quality but are not fabricated when unavailable.

The worker maintains up to 14 upcoming daily publications from validated, unused observations. It avoids a station used in the prior 30 days when alternatives are available and varies broad region, launch cycle, and profile quality. It also compares measured thermodynamic layers against recently published profiles and prefers a less similar candidate when data quality is comparable. If a candidate is unsuitable, the worker records why and tries another verified candidate; it never invents one.

## Navigation and visual system

The four destinations are Home, Play, Rankings, and Profile. Active chart and map steps use an immersive layout. The existing Skew-T renderer and MapLibre style are reused. The result reveals station metadata, both locations, a connecting line, distance, score, observation time, provenance, and two to four concise deterministic insights.

## Explicit exclusions

Radar, forecast competitions, satellite challenges, social/community features, chat, head-to-head play, paid content, ads, and standalone weather utilities are outside this release.
