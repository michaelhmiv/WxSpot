# Sounding Hunt acceptance checks

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
