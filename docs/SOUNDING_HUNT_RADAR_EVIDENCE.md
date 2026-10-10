# Sounding Hunt: time-matched national radar and advanced sounding

This implementation is on PR #12 and is **not** a production deployment.

## Backend contract

- `GET /game/sounding-hunt/today` and practice/historical sounding responses now contain a station-redacted `diagnostics` object calculated by the existing MetPy 1.7.1 engine; CAPE/CIN, PWAT, LCL/LFC/EL, DCAPE, shear, SRH, hodograph storm motion, markers, guides, and full observed levels come only from validated IGRA records. Inadequate profiles return explicit missing reasons.
- `GET /game/sounding-hunt/radar/{kind}/{identifier}/frames` requires guest authorization and scopes `daily` to a released challenge, `practice` to that player's session. It checks the IEM archived N0Q PNG for each of 13 UTC time slots in ±30 minutes around launch and returns only verified frames.
- `GET /game/sounding-hunt/radar/{kind}/{identifier}/tiles/{stamp}/{z}/{x}/{y}.png` only allows frames in the challenge's launch window. It proxies the historical IEM N0Q WMS-T (not current radar), validates PNG bytes, bounds tile zoom/indices and returns a private cache response. HTTPS upstream is fixed and cannot be chosen by users.
- `GET /game/sounding-hunt/radar/{kind}/{identifier}/site/{site}/{product}/{tilt}/frames` inventories **actual historic Level III scan timestamps** within ±30 minutes of launch, using the existing `NexradLevel3Provider._list_day`. Modern N0B/N0G super-resolution reflectivity/velocity and legacy N0Q/N0U are supported; N0S storm-relative velocity, N0C CC, N0X ZDR and N0K KDP retain their original decoder, and N0–N3 tilt codes are checked.
- `GET /game/sounding-hunt/radar/{kind}/{identifier}/site/{site}/{product}/{tilt}/tiles/{code}/{stamp}/{z}/{x}/{y}.png` pins each verified scan's exact product code, time and site; rejects attempts to retrieve arbitrary dates, elevations, products or radar tiles. Both national and local raster tiles authenticate with the user's existing guest bearer.
- Archive: https://mesonet.agron.iastate.edu/docs/nexrad_mosaic/ . Authenticated requests are strictly scoped to game observation identity; coordinates and radar station names are never part of public challenge metadata.

## Android design

- The game's sounding screen now has a draggable divider with an initial 60/40 sounding/radar split, no additional navigation tabs, and no time/tool penalties.
- Sounding supports a Skew-T/hodograph switch, core diagnostics, expanded index list and every original observed pressure level.
- Radar is a MapLibre CONUS overlay with chronological scrubber, animation, previous/next scan, and a launch-time reset.
- Full-country MRMS overlays provide 2-minute rate evidence, 1-hour, 3-hour and 24-hour accumulated rainfall at an hour/biennial sample appropriately close to launch. Selected radar and precipitation toolbars appear over the map rather than shrinking the map canvas. Players can tap the map to select a nearby NEXRAD radar and use product chips (dBZ, Velocity, SRV, CC, ZDR, KDP) and N0–N3 tilt controls. Time labels are UTC and derive from verified archived files; unavailable data never display a substitute.
- The separate Guess map remains the pin-placement flow; score and leaderboard rules are unchanged.
- The radar MapLibre tile client injects the existing guest bearer only for the original API's radar path; this avoids exposing tokens through tile query strings.

## Outstanding verified-release gates

National reflectivity and individual-site historical Level III products (modern/legacy reflectivity, velocity, storm-relative velocity, CC, ZDR, KDP and low-elevation N0–N3 scans) are now implemented in the branch. **Historical Level III rendering is still subject to live source and Android device acceptance**; modern product parsers need test-data confirmation, and some selected site/tilt/time combinations legitimately have no scan. Historical 2-minute precipitation (rate proxy), 1-hour, and 24-hour MRMS rasters are now supported through verified dated IEM archive PNG and WGS84 world files; three-hour totals are derived from three actual one-hour accumulation grids rather than from reflectivity. Real 2026-09-09 archival records passed raster rendering on the GitHub runner. All must be explicitly unavailable when archive files are absent, and georeferencing must be verified per image. The rain-rate image uses a 2-minute accumulation palette, and meteorological interpretation should distinguish amount from derived hourly equivalent; the original source is not an instantaneous rain-rate observation. The raw Level II volume-scanning interface is not implemented.

Before promoting the build, verify IEM availability and historical WMS-T with a live test, exercise the Android map raster loading on API 30/36 and a physical Pixel, verify UI accessibility/gesture precedence and smooth scrubbing, inspect actual screenshot evidence, test private practice-scoped tile URLs, and re-run backend and Android CI. Preserve draft status and production isolation until then.

Known data nuance: IGRA sounding levels span balloon ascent; the matching national radar is initially the closest five-minute archive frame at/before launch, and the ±30-minute timeline provides context. This is not a claim that every atmospheric level was observed simultaneously.
