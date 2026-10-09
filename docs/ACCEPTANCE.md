# Sounding Hunt acceptance checks

## Automated CI evidence

Commit `44aa8dd` passed backend tests/lint and the Alembic upgrade, Android formatting/unit/compile/lint/build checks, and the complete ranked-to-practice journey on Android API 30 and API 36. The emulator journey covered a ranked guess and reveal, duplicate rejection, leaderboard, restart recovery, practice scoring, and unchanged ranked statistics. See [backend](https://github.com/michaelhmiv/WxSpot/actions/runs/37947621660), [Android](https://github.com/michaelhmiv/WxSpot/actions/runs/37947621648), and [device](https://github.com/michaelhmiv/WxSpot/actions/runs/37947621649) workflow runs.

These CI checks do not cover staging/production deployment, a real beta signing key, or physical-device chart/map gestures and accessibility. Those remain rollout checks.

## Visual and product identity gates (pending)

- [ ] App launcher/branding remains WXspot (or existing WxSpot Beta label), Sounding Hunt is clearly a game within it.
- [ ] No radar/satellite/model provider, render endpoint, data path, weather worker, or stored weather data is silently removed.
- [ ] Original light-first game theme and designed dark alternative are coherent across Home, Play, Sounding, Guess, Result, Rankings and Profile.
- [ ] Sounding scientific variables, legends/axes, coordinates and missing-value handling remain precise and legible; no fake data.
- [ ] Guess map has an original playful treatment, real geographic accuracy, appropriate attribution, no location-spoiling overlays, and usable touch gestures.
- [ ] Contrast (normal text 4.5:1, large text/UI visual components 3:1), non-color cues, TalkBack, touch targets >=48dp, small phone layout, large text and reduced motion verified.
- [ ] Screen capture/golden comparisons and relevant Compose UI tests complete; physical device screenshots and interaction checks reviewed.

These visual gates are fully specified in [visual redesign plan](WXSPOT_GAME_VISUAL_REDESIGN_PLAN.md). They have **not** been completed by the earlier CI results.

## Daily player journey

- [ ] Launch opens WXspot Home with today's challenge, streak, completion state, and one-tap play.
- [ ] Public challenge contains an actual validated IGRA observation date/time in UTC, temperature/dew point, pressure, and available wind data.
- [ ] Public JSON contains no station ID/name, coordinates, MSL elevation, source URL, or answer metadata.
- [ ] Skew-T touch inspection, pan/zoom, and reset work on a phone; unavailable data are represented as unavailable.
- [ ] Lower-48 map accepts a pin tap and repositioning; coordinate entry accepts signed decimals.
- [ ] Explicit confirmation submits one final official guess and displays loading/error states.
- [ ] Server result has WGS84 distance, versioned score, answer, source attribution, map line, and evidence-based insights.
- [ ] Repeated daily submission returns conflict; guest resume restores completion state.
- [ ] Rankings sort consistently and never show precise guess coordinates.
- [ ] Profile stats/streak/history update from server data.
- [ ] Practice observations are not active/future daily challenges and practice results never alter daily stats or rankings.
- [ ] Historical challenge profile and result access work after competition closes; future chart data is unavailable.
- [ ] Process restart restores guest identity and official result; device date/time does not control challenge identity.

## Backend test coverage

`backend/tests/test_sounding_hunt.py` covers geodesic scoring, numerical validation, DST calendar windows, streaks, station filtering, candidate validation, public response redaction, guest auth/resume, daily result and duplicate protection, leaderboard privacy, and practice isolation. `backend/tests/test_soundings.py` exercises IGRA record parsing, missing/QC values, launch time, unit handling, and the retained native sounding contracts.

Before production rollout, exercise rollover/prefill on staging, concurrent duplicate submission, migration upgrade from the current revision, queue fallback during source outage, and the full Android journey on a physical device.
