# Sounding Hunt: time-matched national radar and advanced sounding

This implementation is on PR #12 and is **not** a production deployment.

## Backend contract

- `GET /game/sounding-hunt/today` and practice/historical sounding responses now contain a station-redacted `diagnostics` object calculated by the existing MetPy 1.7.1 engine; CAPE/CIN, PWAT, LCL/LFC/EL, DCAPE, shear, SRH, hodograph storm motion, markers, guides, and full observed levels come only from validated IGRA records. Inadequate profiles return explicit missing reasons.
- `GET /game/sounding-hunt/radar/{kind}/{identifier}/frames` requires guest authorization and scopes `daily` to a released challenge, `practice` to that player's session. It checks the IEM archived N0Q PNG for each of 13 UTC time slots in ±30 minutes around launch and returns only verified frames.
- `GET /game/sounding-hunt/radar/{kind}/{identifier}/tiles/{stamp}/{z}/{x}/{y}.png` only allows frames in the challenge's launch window. It proxies the historical IEM N0Q WMS-T (not current radar), validates PNG bytes, bounds tile zoom/indices and returns a private cache response. HTTPS upstream is fixed and cannot be chosen by users.
- Archive: https://mesonet.agron.iastate.edu/docs/nexrad_mosaic/ . Authenticated requests are strictly scoped to game observation identity; coordinates and radar station names are never part of public challenge metadata.

## Android design

- The game's sounding screen now has a draggable divider with an initial 60/40 sounding/radar split, no additional navigation tabs, and no time/tool penalties.
- Sounding supports a Skew-T/hodograph switch, core diagnostics, expanded index list and every original observed pressure level.
- Radar is a MapLibre CONUS overlay with chronological scrubber, animation, previous/next scan, and a launch-time reset. Time labels are UTC and derive from verified archived files; unavailable data never display a substitute.
- The separate Guess map remains the pin-placement flow; score and leaderboard rules are unchanged.
- The radar MapLibre tile client injects the existing guest bearer only for the original API's radar path; this avoids exposing tokens through tile query strings.

## Outstanding verified-release gates

The **first supported historical product is the national reflectivity mosaic**. Site-specific Level-II/Level-III velocity, storm-relative velocity, correlation coefficient, ZDR, KDP, and tilt need a separately validated historical decoder, site selection and scan matching. Historical precipitation rate/accumulation products require archival resolution/coverage checks. The API currently declares these products unavailable rather than mislabeling a national reflectivity mosaic as another radar product.

Before promoting the build, verify IEM availability and historical WMS-T with a live test, exercise the Android map raster loading on API 30/36 and a physical Pixel, verify UI accessibility/gesture precedence and smooth scrubbing, inspect actual screenshot evidence, test private practice-scoped tile URLs, and re-run backend and Android CI. Preserve draft status and production isolation until then.

Known data nuance: IGRA sounding levels span balloon ascent; the matching national radar is initially the closest five-minute archive frame at/before launch, and the ±30-minute timeline provides context. This is not a claim that every atmospheric level was observed simultaneously.
