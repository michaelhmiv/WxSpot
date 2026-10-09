# WXspot — Sounding Hunt game-first visual redesign and completion plan

**Status:** IMPLEMENTATION IN PROGRESS — see checkpoint below  
**Prepared:** 2026-10-09  
**Repository:** michaelhmiv/WxSpot  
**Target:** Existing draft PR #12, branch feat/sounding-hunt-rebuild, based on inspected head 34e1f9235bc7a2bb5bf8baabe1a8cca10279aa33. Re-check branch HEAD before implementation.  
**Application:** WXspot / Weather Spot (retain existing Android package, brand, and signing lineage).  
**Game:** Sounding Hunt (one game within WXspot).  
**Game tagline:** Read the atmosphere. Find the location.

## 0. Agent mandate and non-negotiable decisions

This is a handoff-ready specification for the coding agent finishing PR #12, not a claim that the visual redesign is already implemented.

- Create a highly polished **original, cheerful weather-strategy game**. Visual inspiration: the optimistic low-poly color, clean geometry, miniature world-building, and satisfying tactics-game feel of The Battle of Polytopia. Do NOT copy its sprites, terrain tiles, characters, music, fonts, layouts, trademarks, or proprietary art. Design original WXspot weather motifs.
- WXspot is the app. Sounding Hunt is the flagship game and can occupy the entire current foreground experience (Home / Play / Rankings / Profile). No full general-weather dashboard is required this release. Future games and utilities must still fit under the WXspot brand.
- **Preserve the weather platform.** Radar, satellite, model, sounding, station, weather-render, tiles, ingestion, and legacy data/API capabilities are not to be deleted or decommissioned. The current PR removed old WEATHER UI navigation but retained backend routes. Make that distinction clear in code/docs. Other weather data can power future game modes.
- Retain the scientifically accurate observed radiosonde data, native Skew-T/log-P geometry and wind data, geodesic scoring, anti-leak boundary, 08:00 Eastern daily rules, practice isolation, MapLibre geographic accuracy, existing backend/worker/PostGIS, and migration strategy. Do not replace science with cartoon approximations.
- Existing interactive radar/satellite/model tooling is **not** mandatory as top-level navigation for this game-first release. Any illustrative weather on decorative surfaces is explicitly not live meteorological data.
- Do not add account mandates, ads, coins, loot boxes, purchases, competitive score manipulation, new backend services, heavy animation engines, or unnecessary infrastructure.
- Do not merge PR #12 or deploy production before required gates. Do not remove historical weather screens/data merely to simplify game UI. Avoid altering production Railway as part of visual-design implementation.

## 1. Verified starting point and audit

### 1.1 What is already built

PR #12 implements a game-first Android client, daily challenge, unlimited practice, guessing map, explicit confirmation, post-guess reveal, scores, leaderboard, profile, history, and sharing. Backend has server-authoritative WGS84 geodesic scoring and versioned scores, private/public DTO separation, additive Alembic revision 0006_sounding_hunt, bounded NOAA/NCEI IGRA 2.2 ingestion and candidate queue. Existing guest identity, MapLibre, Kotlin/Compose, FastAPI/PostGIS, Railway API/worker and legacy weather providers are reused.

CI evidence from PR description at 34e1f923: backend Ruff/Alembic/108 tests + 5 live-source checks passed; Android checks and builds passed; emulator journey passed on API 30 and 36. These results predate this design implementation and **must be rerun after changes**.

### 1.2 Direct code audit and specific deficiencies

| Surface / code | Observed implementation | Required correction |
| --- | --- | --- |
| MainActivity.kt | One MaterialTheme with a hardcoded darkColorScheme and generic Material typography | Install WXspot game design system; support intentional warm light default and accessible dark mode; unify system bars and theme |
| SoundingHuntApp.kt: globals/Scaffold | Ink #0B1220, Panel #142033, cyan/mint/gold, dark navigation; ~963-line single UI source | Extract semantic tokens, reusable game components and per-screen compositions; design navigation bar rather than default Material style |
| HomePage / DailyHero | Generic ElevatedCard, text-led hero, plain stat pills, no visual sense of exploring a weather world | An illustrated daily expedition/quest hero, strong hierarchy, mission CTA, readable streak/ready/completed state, charming original weather motif |
| PlayPage | Two near-identical text cards for ranked/practice | Two distinct, tactile mission cards; ranked vs practice clearly differentiated by label, icon, supporting graphic and rules |
| SoundingPage and SoundingView.kt | Scientific Skew-T has a literal dark Canvas background; chart uses fixed 310dp Canvas height and touch inspection | Place plot inside a purposeful high-legibility science instrument panel; responsive layout and reliable gestures; preserve axes/units/profile accuracy, missing data and winds |
| GuessPage | Raster MapLibre view, plain circle marker, two coordinate text fields, default confirmation button | A bright original geographic game-board treatment, distinctive selectable pin, map controls, selected-coordinate feedback and safe-area handling; no revealed station hints |
| backend/wxspot/main.py /weather/style | Raster basemap explicitly saturated at -0.75 and raster brightness capped at 0.42 | Expose game-specific light map styling independently from any existing weather layers; keep basemap attribution and accurate lat/lon; avoid recoloring data rasters |
| SoundingHuntMap.kt | Generic circle markers #FDE68A/#67E8F9, slim cyan line, fixed initial center/zoom | Original guess/answer pin designs, clear distinction, result fit bounds, robust map lifecycle; maintain geo accuracy and touch performance |
| ResultPage | Score shown as text in dark panel; utilitarian station info and 270dp reveal map | Satisfying deterministic score-reveal sequence, short motion with reduce-motion fallback, prominent distance and station, side-by-side comparison with legible science clues |
| RankingsPage | Plain numbered rows in ElevatedCard | Distinct top-three podium/medallion emphasis and compact accessible list for everyone else; exact ranking/scoring untouched |
| ProfilePage | Generic stat cards and history rows | Explorer/journey identity with tasteful achievements/streak visuals; only show earned server-based stats |
| Loading/empty/error | Default spinner and text banners | Designed illustrations/decoration and actionable messages, no false offline or loaded state |
| Tests | CI unit/lint/build and emulator workflow exist; screenshots collected | Add visual snapshots/golden baseline review, semantic navigation states, accessibility checks and map/chart manual-device gates |

All paths above refer to current branch code inspected 2026-10-09. Verify behavior during implementation; this is a source audit, not a physical-device UX test.

### 1.3 Infrastructure inventory (read only, 2026-10-09)

Railway project **WxSpot (WeatherSpot)**: only **production** environment is present. WxSpotAPI, WxSpotWeatherWorker, and PostGIS are online; each has one successful deployed replica and no recent failures in the 24-hour window checked. API and worker deploy from the main branch. PostGIS uses its existing persistent data volume, and WxSpotMedia bucket remains present. PR #12 has not been deployed into production. No staging environment is configured. Creating a staging environment must isolate its database and credentials; **never point a staging worker at production DB**.

## 2. Product identity and reference direction

**WXspot:** welcoming weather-game platform. App icon, splash, launcher label, package name, identity and parent navigation refer to WXspot (respect existing beta label where needed). **Sounding Hunt:** named game with its own icon/title/subtitle and daily/practice states. Its tagline appears *inside the game*, not as a mandatory platform-wide slogan.

The desired reference is The Battle of Polytopia's geometric friendliness and inviting miniature-world energy, not a clone. Original motif: **Sunlit Atlas** — cheerful cloud archipelagos, geometric rolling landforms, wind ribbons, sun-path arcs, contour lines, faceted terrain silhouettes, and a little compass/balloon mark. Use original SVG/vector/Compose Canvas drawables only, authored in repo and source controlled. A weather balloon icon can signal Sounding Hunt without implying a fictional observation.

**Personality:** clever, curious, adventurous, optimistic, slightly tactile, competitive but non-aggressive. Weather data is professional and measured, never artificially recolored to increase drama. Avoid gloom, generic SaaS dashboards, neon-on-black everywhere, childish weather mascots, faux instrumentation, flashy slot-machine reward patterns, and skeuomorphic fake sensors.

Reference (design inspiration only): https://polytopia.io/ . Brand/asset permissions: https://polytopia.io/brand-assets-guide-lines/ . No Polytopia media shipped or committed.

## 3. Design system — mandatory implementation

Implement a semantic-token-based design system in Android, not ad-hoc Color() literals copied between screens. Organize under android/app/src/main/java/app/wxspot/ui/theme/ and ui/components/ or equivalent tested package, e.g. WxSpotTheme, WxColors, WxTypography, WxShapes, WxSpacing, GameSurface, QuestCard, PrimaryGameButton, StatChip, Badge/Medal, WindDecoration, GameNavigation.

### 3.1 Palette (starting values, refine against contrast checks)

| Token | Light theme | Purpose |
| --- | --- | --- |
| sky | #75CBF2 | Optimistic brand sky and neutral atmosphere |
| meadow | #A4D98A | Calm land, completed state supporting shade |
| sunshine | #FFD16A | Energy, daily mission emphasis |
| coral | #F39B76 | Warm accents, highlights |
| violet | #A99CE2 | Practice/secondary game distinction |
| cloud | #F8F4E7 | Main warm light background |
| paper | #FFFEF8 | Data/reading card surface |
| ink | #263547 | Primary text and dark outlines |
| slate | #526579 | Secondary text |
| ocean | #3E91B8 | Accessible interactive accent; tune for contrast |
| forest | #286A5F | Success/dark accent |

These are exploration starting tokens, **not pre-verified accessible foreground/background pairs**. Audit all rendered text/button/chart combinations at WCAG AA normal text >=4.5:1, large text and UI strokes >=3:1. In particular do not set light sky, sunshine, or meadow as text on white. State/error/danger uses independent dark text and icon/label, never hue alone.

Default to a **bright warm light** game shell. Create an intentionally composed dark theme, not an automatic inversion. Data visualization may use its own stable high-contrast palette in both modes. Use subtle 2–3 shade planar fills, bold outline shadows and controlled depth rather than continuous noisy gradients.

### 3.2 Shape, depth, type, composition

- Tactile game tiles: primary mission cards radius approximately 20–28dp; supporting cards 14–18dp; chunky but not childish. Original faceted corner notches/offset shadows used sparingly.
- Elevation comes from strong shapes, soft hard-edged shadow offsets or two-plane vector shading; reserve custom draw operations for highly visible elements. Avoid excessive nested ElevatedCards.
- Readable display font personality from a properly licensed font or bundled system fallback; default robust sans for data, charts, dates, coordinates and buttons. No licensed game fonts copied. Define a complete type scale including compact labels, game hero, score, card heading and dense science labels.
- Establish spacing tokens (4, 8, 12, 16, 24, 32dp), baseline visual rhythm, consistent left alignment and predictable surface margins. Support small 320dp-wide Android layouts and large text.
- Button states: tactile filled primary, outlined secondary, loading, disabled, pressed, focus, success. Touch targets >=48dp; visible focus states and haptics only where appropriate and user-enabled.
- Custom bottom navigation can remain Home / Play / Rankings / Profile with proper TalkBack labels and clear selected state. Keep it bottom-aligned and never obscure interactive map/chart.
- Include original launcher/brand mark treatment in app UI and icon variant concept; do not change signing/package IDs to effect a rebrand. Build reusable original weather decorations as light-weight vectors.

### 3.3 Illustration and animation discipline

Provide a small coherent weather-world illustration set: illustrated daily quest hero; sun/cloud/balloon/compass/terrain motifs; streak flame or sunburst; score medallions; map pins; tasteful empty states. Mark all non-data illustration layers as decorative; decorative clouds/terrain are **not** live radar or forecast.

Implement restrained motion: card press (<200ms), route/state transitions (~150–250ms), result score count/medal flourish only after confirmed server result (~400–800ms); use Compose built-ins when possible; respect system animator scale/reduce-motion/transition-disabled state; never delay showing an actual result and never derive the result score client-side.

## 4. Screen-by-screen target UX and required behavior

### 4.1 Home — today’s weather expedition

Top-left app brand WXspot; a Sounding Hunt heading or game mark is distinct. Decorative sunny sky/terrain header using original vectors; large **Today’s Hunt** quest card with challenge number, ready/completed state, one obvious Play/View Result CTA, rule text (one ranked guess; 8 AM Eastern rollover). Display honest streak and recent result. Clearly secondary unlimited-practice entry. Skeleton/empty/source-unavailable state retains atmosphere and actionable retry, not a false quest.

### 4.2 Play — choose mission

Two visually distinct selectable quests: **Daily Hunt** (ranked, shared challenge, one official attempt) and **Practice** (unlimited, unranked). Represent with original balloon/compass or map/science motifs, not paid-game loot. Each card shows plain rules and strong action. Historical review remains accessible. Avoid a second redundant Home clone.

### 4.3 Examine sounding — serious weather instrument in a cheerful shell

A high-contrast science instrument panel over the light game background. Keep actual Skew-T/log-P axes, observed temperature/dew point, pressure (hPa), winds, missing-data representation, launch/nominal UTC wording, and interactive touch/zoom/reset. Preserve original numerical transforms, measured values and diagnostics; styling cannot alter physics. Draw readable axes/labels with independent data color tokens. Ensure the plot uses available vertical space on phones; remove accidental clipping from fixed 310dp assumptions where appropriate; preserve scroll/cursor interaction. Include a compact plain-language help affordance explaining plotted variables without giving location cues. A visible **Choose location** action stays pinned above safe area while not obscuring chart.

### 4.4 Guess map — beautiful *accurate* game board

The map is still real geographic coordinates and continental U.S., not a fabricated polygon world. Build a **light game-specific map style** that keeps coastlines, state boundaries, labels and meaningful terrain distinct; a faceted border/background can make it feel like a strategy board. Current /weather/style intentionally desaturates and darkens the raster basemap; do not globally replace that style for weather analytical views. Prefer a distinct /weather/style/game or parameterized style, with explicit cache semantics, OSM attribution, and no breaking changes to legacy consumers. Verify raster-source tile licensing/capabilities before planning dynamic palette recoloring. If source is raster-only, use minimal raster brightness/saturation correction and non-geographic decorations outside the map instead of pretending pixel recoloring creates vector terrain.

A visually distinctive **selected guess** marker, crosshair and high-contrast confirmation state replace generic circles. Support pan/zoom/tap, coordinate entry, reselect and validation; keep selected marker visually above decorative layers; show coordinates consistently and do not hide accuracy beneath animations. Answer location, station identity/elevation, true station layers and any location-revealing weather overlays MUST NOT be accessible prior to submission. The map must remain usable without art assets loading.

### 4.5 Result reveal — earned excitement, not spectacle

Immediately show actual server score (0–5000), distance, correct station/state, preexisting WGS84 route line and original guess, then animate only presentation if motion allowed. Introduce score medal/crest tiers as **client presentation only**, never change score calculation or competitive rules. Map distinguishes player pin/answer pin through shapes + labels (not hue only); fit bounds to both safely. Present two to four existing evidence-based sounding insights prominently, include observation/source time/provenance, allow chart review, spoiler-free sharing, leaderboard and practice. Distinguish historical review and practice from daily rank explicitly.

### 4.6 Rankings and Profile

Top-three podium visual on rankings when three actual entries exist, scrollable compact rows for all ranks, current player highlighted with accessible text. No imaginary competitors or player avatars. Keep server sort exactly score, distance, time, ID. Profile emphasizes personal expedition record (played, best, average, current/longest streak, average error, history) and guest identity caveat. Decorative medal visuals require actual statistics; no fictitious collectible economy.

### 4.7 Cross-cutting

Design all loading, empty, no connection, source outage, authorization, signed-out/guest restart, duplicate submission, state restore and large-font screens. Empty/error state artwork must not misrepresent scientific data. Preserve bottom navigation and immersive chart/guess/result steps.

## 5. Weather data, radar and forward compatibility

**Keep existing radar, satellite, models, /weather/catalog, /weather/frames, /weather/render/*, /weather/style, /weather/soundings, and worker/provider pathways available.** Do not delete unused code, route contracts, data artifacts or workers as a collateral effect of the game UI rewrite. Protect API compatibility and future modes with existing smoke/regression tests.

For this release, Sounding Hunt is **radiosonde-driven**. Radar/satellite/model feeds are not required to make guesses or change scoring and should not be surfaced to a player as station-revealing overlays before a ranked attempt. A possible **post-reveal Learn More / Atmospheric Context** panel may be considered only if:
1. The weather snapshot is truly available for the relevant observation time and a confirmed product, not a present-day frame presented as historic.
2. Every layer includes provider, valid time, legend/units, and missing-data fallback.
3. It does not slow core gameplay or create additional ongoing hosting cost without review.
4. It is clearly optional and fails gracefully.

Do not make this optional panel a blocker if historical layer data are unavailable. Preserve the future ability to build radar/satellite/model-based games under WXspot without reconverting the app to an analytics dashboard.

## 6. Engineering sequence / PR work packages

### P0 — protect architecture and fix messaging

1. Re-read PR #12 diff, product spec, API docs, architecture and repository tree. Audit what exactly legacy UI removed versus weather backend retained; do not make unsupported assumptions.
2. Ensure READMEs and specs consistently say **WXspot (app) / Sounding Hunt (game)**; remove statements that imply permanent abandonment of radar, satellite or models. Scope current UX as game-first, not weather-utility-first.
3. Create this design system plan as implementation source of truth and retain release notes checkpoint.
4. Keep PR as draft until all release gates are complete. Every work-package merge stays on feat/sounding-hunt-rebuild; do not modify main independently.

**Acceptance:** names correct throughout current docs, application launcher still WXspot, weather-provider regression/compatibility established.

### P1 — foundational theme + original art

1. Implement ui/theme semantic color tokens with accessible light default and deliberate dark variant.
2. Implement typography/shape/spacing/elevation/state tokens and create WXspot game surface/component library.
3. Add original vector graphics (balloon, sun/cloud, terrain ribbons, compass, medals, pin); document source/licensing in repo. No third-party game assets.
4. Update MainActivity, system bars, MaterialTheme and app shell. Eliminate direct hex constants from primary screens and map styles except within designated palette definitions.
5. Design and test bottom nav, primary/secondary buttons, state chips, headers, reusable mission cards, metric tiles, empty states.

**Acceptance:** no generic unthemed core component remains, all interactive states visible, light/dark readable; render previews or screenshot artifacts for each component.

### P2 — full screen redesign

1. Home quest hero, stats/history and brand hierarchy.
2. Play daily/practice mission cards and archive affordances.
3. Sounding instrument panel and layout/legend/help while preserving scientific rendering and data.
4. Guess screen, selected state, coordinate controls, safe-area and final confirmation.
5. Result scoreboard, animations, correct-station reveal, map, insights and share.
6. Rankings and Profile custom game components plus handling of loading/empty/errors.
7. Pull UI out of the 963-line SoundingHuntApp monolith into readable per-screen files; keep state in SoundingHuntViewModel with minimal behavior changes.

**Acceptance:** end-to-end journey runs on light/dark, 320dp and standard phone widths, portrait, larger system text; all game and guest state tests remain green.

### P3 — geographic design and weather-integrity

1. Introduce a separate light game-specific MapLibre style; preserve /weather/style compatibility and provider/API contracts. Inspect existing raster tile attribution and cache config.
2. Original game marker sources/layers, pin labels, result route and zoom bounds, OSM attribution, zoom/touch lifecycle.
3. Assess label readability, map loading failures, network/back navigation, gesture conflict and color-blind differentiation.
4. Cross-check public/pre-guess payload and rendered map against spoiler leakage: no station details, elevation, source ID, unapproved radar layers or hidden answer metadata.
5. Keep measured sounding thermodynamics and wind data stable; add snapshot/contract assertions to detect chart mislabeling.

**Acceptance:** a guess has unchanged numeric coordinates/geodesic result before vs after restyle; no pre-guess answer leakage; map providers remain functional.

### P4 — polish, test automation and measurable quality

1. Add Compose UI tests: app/game labels, navigation, ready/completed/practice/review, error/empty, guess confirm and replay, state restore, large text and TalkBack content descriptions.
2. Add deterministic light/dark screenshots covering Home, Play, Sounding, Guess, Result, Rankings, Profile and significant empty/loaded states. CI uploads comparison artifacts; choose a maintainable golden approach with reviewed baseline and narrow tolerance. Never claim screenshot tests passed until run.
3. Retain backend pytest/Ruff/Alembic checks and Android Spotless, unit, lint, debug/release assembly and API 30/36 journey tests; add new checks without replacing existing journeys.
4. Test 320dp viewport, >=200% font scale where practical, color-blind readability, WCAG contrast audit, 48dp touch targets, reduce-motion, offline/error, process death/recreation, map gestures, chart pinch and pointer behavior.
5. Performance: keep scrolling and map interaction responsive; target 60fps on normal devices, avoid expensive per-frame Compose recompositions, don't load huge bitmaps or animations, and record frame/jank before/after on test phones. These are targets requiring measurement, not claims.
6. Verify score math and result replay unchanged by UI retheme; visual flourishes cannot alter rankings.

**Acceptance:** all CI green on the final SHA, reproducible screenshot evidence, no regression in scientific or game contracts, manual-device checklist signed off.

### P5 — safe staging, production readiness and rollback

1. Current Railway has production only; propose dedicated staging environment with isolated DB/volume/bucket/credentials and API/worker deployed from the PR branch, or an explicitly separate low-cost project. Never reuse production database or run staging worker with production credentials. Verify Railway setup and costs before changing infra.
2. Confirm backend migration from revision 0005 to additive 0006 on staging; protect existing production data.
3. Let bounded real IGRA ingest populate current challenge and next ~14 days, inspect low-pool status, rejection reasons, candidate diversity, and provenance. No fabricated weather.
4. Exercise one official attempt, duplicate rejection, practice, leaderboard/profile, guest restore, pre-guess sanitization, Eastern 08:00 boundary including DST, source outage and recovery, and server/client update compatibility.
5. Physical-device review: chart touch/pinch, map tap/pan/zoom/coordinate edit, screen density/font, load/timeout recovery, lifecycle and accessibility; capture screen recordings/screenshots and verify with design brief.
6. Existing beta keystore/credentials are not in the development workspace; establish legitimate existing signing lineage from the designated release workflow. NEVER commit secret keys or present review debug APK as update-compatible.
7. Merge/release only once API/worker/android build and staging checks pass. Preserve previous Railway service/code/data and legacy weather providers for rollback. Do not downgrade/drop additive game tables once results exist; rollback code without destructive DB changes.
8. Capture final PR summary, diff, check links, screenshots, rollout checklist and known limitations.

**Acceptance:** a human-approved release candidate backed by verified staging and physical-device acceptance; production still untouched until rollout decision.

## 7. Detailed quality matrix

| Scenario | Verification |
| --- | --- |
| App identity | Launcher label WXspot / WxSpot Beta per variant; package IDs and signer unchanged |
| Hierarchy | Game title Sounding Hunt within WXspot, not app title |
| Weather continuity | Radar, satellite, models, style, render and existing workers/routes persist; no unplanned decommission |
| Scientific integrity | IGRA observed data unchanged; measured T/Td/pressure/wind axes/units, missing data explicit |
| Competitive fairness | One ranked guess, practice isolation, 0–5000 server WGS84 score unchanged |
| Confidentiality | No pre-guess station name, coordinate, elevation, answer-source metadata, revealing geo overlay |
| Usability | Clear CTAs, readable game shell, zoomable chart/map, typed coordinates, big-text and small screen |
| Accessibility | TalkBack labels, focus, contrast, shape/labels independent of color, motion preference |
| Failure | NOAA outage, empty challenge, slow network, map tiles unavailable, process death, retry and restore |
| Visual QA | Original art, coherent theme across seven primary screens, screenshot baseline review |
| Infrastructure | Railway isolated staging, real queue and migration, production untouched before approval |
| Release | CI complete, physical device, legitimate beta signing, documented rollback |

## 8. Deliverables and definition of done

**Required repository deliverables:**
- A living game visual design source-of-truth document (this file) and updated WXspot naming/scope descriptions.
- Implemented Android game theme and reusable components, original drawable/vector assets, and all seven screens restyled.
- Game-specific map style without overwriting legacy weather map requirements; preserved science/chart behavior.
- Automated regression + screenshot evidence and expanded manual acceptance checks.
- A refreshed PR #12 summary listing precise completed work, latest passing CI links, release blockers, staging artifacts and test evidence.

**Definition of done:** visual character is recognizably original, bright and strategic; gameplay is easy to understand; scientific data remains accurate and legible; core Android/device and backend checks pass; weather platform remains intact; protected game data remain private before guess; staging and physical-device tests are verified; and a release can be signed with the existing beta key. Until then mark PR draft and **do not claim release-ready**.

## 9. Coding agent execution instruction

Work on existing PR #12 branch. Begin by reading this entire plan, the current product/API/architecture/deployment/acceptance docs, theme and UI sources, and the latest head/CI. Implement P0–P4 fully, update tests/docs, run/fix every relevant check, and only then undertake staging validation when it can be safely isolated. Commit coherent work packages to the current PR branch. Do not stop after a planning response. Avoid unrelated feature expansion. If an unavailable keystore, staging privilege, or physical device blocks full release, document that accurately and leave the branch safely in draft without deploying production. Do not substitute generated mock data for real observed weather.


## 10. Execution checkpoint — 2026-10-09 (implementation versus acceptance)

The coding implementation has started directly on PR #12. These are implemented source changes, not merely design proposals:

- Kotlin WXspot original theme in `ui/theme/WxSpotTheme.kt` includes light/dark semantic palette, Material button/surface role coordination, shape/typography scale, and the unchanged WXspot app identity.
- `ui/components/WeatherWorld.kt` includes original Compose-rendered geometric sun/cloud/landscape/balloon artwork and a score medallion. No Polytopia proprietary assets were used.
- `SoundingHuntApp.kt` uses semantic visual roles and refreshed expedition/game navigation, Home, Play, stats, score, leaderboard and profile treatments; scientific detail remains readable in a separate chart surface.
- `SoundingHuntMap.kt` targets a separate `/weather/style/game` basemap; `backend/wxspot/main.py` retains the old `/weather/style` while adding a bright style for guessing. Map data still uses actual geographic positions.
- `backend/tests/test_sounding_hunt.py` asserts the legacy map style remains unchanged, the new style is distinct, and no station metadata enters the map style.
- `SoundingHuntJourneyTest.kt` now asserts WXspot identity and saves emulator screenshots at Home, Sounding, Guess, Result, Rankings, Play and Practice; the device script retrieves screenshots.

**Verified:** prior game baseline CI passed; isolated Railway staging created with its own PostGIS/database, S3 bucket, API and worker; real NOAA IGRA maintenance logged 96 validated candidates, 14 queued challenges, and 82 practice candidates; the [staging API acceptance run](https://github.com/michaelhmiv/WxSpot/actions/runs/37966780349) passed. Production remains on main with no migration applied.

**Still open:** final post-redesign Android format/build/lint and emulator acceptance runs must finish and be reviewed; additional pixel/golden review, legibility at large font sizes and on small physical phones, full map-chart gesture QA, source-outage/08:00 DST rollover staging validation, beta signing/update compatibility and release decision. Do not mark P0-P5 wholly complete or merge on staging API success alone.
