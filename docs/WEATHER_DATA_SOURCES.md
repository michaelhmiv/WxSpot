# Weather data sources

Source notes updated 2026-10-08. Radar, satellite, HRRR/GFS, forecast/observed soundings and NWS location weather have passed source-specific hosted checks and are merged. The integrated beta matrix is recorded in BETA_ACCEPTANCE.md; physical Pixel performance remains unmeasured. Revalidate services before expanding products.

## Implemented: NOAA/NWS RIDGE2

Authority: [NWS radar FAQ](https://www.weather.gov/radarfaq), [NWS CloudGIS](https://www.weather.gov/gis/cloudgiswebservices), and [GeoServer directory](https://opengeo.ncep.noaa.gov/geoserver/www/index.html).

Endpoint: https://opengeo.ncep.noaa.gov/geoserver/{site}/ows. WMS GetCapabilities 1.3.0 supplies layer names and ISO8601 time dimensions. Implemented NEXRAD products are `{site}_sr_bref` and `{site}_sr_bvel`. GetMap uses WMS 1.1.1, EPSG:3857, an explicit TIME, transparent PNG, and longitude-safe projected bounding boxes. Scan cadence varies with radar operation; do not infer scans at uniform intervals. KCLX advertised 23 scans over roughly two hours at inspection. Parse the advertised frames, never manufacture timestamps. Single-site elevation is not advertised reliably and remains null, rather than assuming 0.5°.

Client consumes direct immutable-time WMS tiles while live. API caches capability metadata for 45 seconds and preserves a georeferenced 1024-pixel WMS raster at publication for replay. Display attribution “NOAA / National Weather Service.” No published request quota or availability SLA was found. Bound concurrency and timeouts; expect XML exceptions, delayed scans, missing sites/products, and time eviction. Check exact advertised membership before capturing because nearestValue can select a different frame. Data is public federal weather data; our service adds no claim of official endorsement.

The Phase 2 registry retains this compatibility provider alongside MRMS, NEXRAD Level III, GOES and HRRR/GFS. The RIDGE2 catalog exposes reflectivity in dBZ and base radial velocity with the provider's scale, not physical m/s. It does not claim nationwide coverage, numeric coverage bounds, or a fixed elevation. Generic frame IDs include source type and provider before the preserved v1 site/product/time identity; capture accepts both identity forms and regenerates the source URL from validated fields. `/weather/radar/frames` remains the compatibility contract for existing builds.

NOAA GetLegendGraphic supplies the provider color scale; frame metadata and captured layer metadata retain its URL. Reflectivity reports dBZ. The velocity WMS capabilities and legend inspected do not unambiguously advertise physical units, so the slice labels the provider scale and never guesses m/s or knots. Elevation remains unspecified for the same reason.

## Implemented: NOAA MRMS national products

The adapter reads exact GRIB2 objects from the public [NOAA MRMS S3 bucket](https://noaa-mrms-pds.s3.amazonaws.com/) and its per-product CONUS inventory. It uses the timestamp in each object key, then checks that timestamp against the GRIB validity time. It does not use the latest-only QPE image service as a historical timeline source. The [NOAA MRMS operational product table](https://www.nssl.noaa.gov/projects/mrms/operational/tables.php) defines the upstream product identifiers and grid metadata.

The selection maps to `MergedReflectivityQCComposite_00.50` (dBZ), `PrecipRate_00.00` (mm/hour), and `RadarOnly_QPE_01H_00.00`, `_03H_00.00`, and `_24H_00.00` (mm). Accumulation frames retain their product-specific window start and end. The adapter preserves grid scan direction and projection, masks non-finite values and documented missing sentinels, exposes CONUS coverage, and bounds object size, inventory, concurrency and in-memory render caches. It serves a rolling three-hour timeline; freshness thresholds differ by product cadence. Exact publication capture decodes the selected GRIB frame and stores its rendered image with the post.

## Implemented: NEXRAD Level III local products

The adapter reads public NEXRAD Level III objects from the [Unidata S3 mirror](https://unidata-nexrad-level3.s3.amazonaws.com/). [MetPy Level3File](https://unidata.github.io/MetPy/latest/api/generated/metpy.io.Level3File.html) decodes NIDS files; local NOAA Level III files are identified by station, product code, tilt code and time. The inventory is limited to the latest three hours and to N0–N3 tilts. Coverage stays local to the selected station.

The six products are product 94 reflectivity (dBZ), 99 base radial velocity (m/s), 56 storm-relative velocity (kt), 161 correlation coefficient (unitless), 159 differential reflectivity (dB), and 163 specific differential phase (degrees/km). Product 56 is rendered using its own discrete data classes and header legend levels; it is never synthesized from regular radial velocity. The decoder reads the actual elevation, site coordinates, radial geometry, first-gate offset, range-bin scale, and product-specific missing/range-fold classes. Missing gates remain transparent; folded gates receive a distinct range-fold treatment. A requested capture is checked against its product, station, time and actual elevation before its image is archived.

This implementation adds bounded GRIB/NIDS object sizes, limited inventories and decoded/render caches, and runs CPU-heavy decode/render work in worker threads. GRIB and Level III objects are still fetched on demand by the API; a source outage or an expired upstream object can prevent a new frame or post capture. Posts with an existing saved image remain replayable. The branch includes six public NOAA sample fixtures and a live NOAA smoke test for all five MRMS products. P2-04 passed backend/PostGIS/live-source, Android and native-device checks in PR #6; source-specific evidence is recorded in PHASE2_STATUS.md.

## Implemented: official NWS alerts

Authority: [NWS API documentation](https://www.weather.gov/documentation/services-web-api) and https://api.weather.gov/openapi.json. `/alerts/active` returns GeoJSON with identifiers, event, severity, sent/effective/expiry, senderName, headline, and geometry. API uses a descriptive User-Agent, requests application/geo+json, and caches for 45 seconds. The documented rate limit is intentionally unpublished; obey upstream errors and retry later. Alerts change asynchronously; expiration is evaluated at display time. API alert history is seven days, not a complete archive. Some alerts lack polygon geometry; the API preserves those records with null geometry and the map renders only supplied polygons. Never fabricate geometry. Preserve official provenance and link to the source.

The alert layer always shows current alerts independently of the radar playback clock. Radar posts do not archive NWS warning history; the layer controls state that distinction. While the map is visible, a local check every ten seconds removes expired cached geometry and closes an expired detail, including during an outage or annotation editing. Returning to the map runs the check immediately. Geometry without a readable expiry is excluded from display.

## Basemap

OpenStreetMap standard raster tiles, WGS84/Web Mercator, with visible attribution and a descriptive client User-Agent. [OSM tile policy](https://operations.osmfoundation.org/policies/tiles/) requires attribution, caching, no bulk/offline prefetch, and reasonable use. This testing default must move to a production tile service or self-hosting before substantial public traffic. URLs/style are configurable. No automatic use of MapLibre demo infrastructure in production.

## Place search: OpenStreetMap Nominatim

The Android client submits searches to `GET /weather/locations/search`; the server calls the configured Nominatim-compatible endpoint and returns canonical names, WGS84 coordinates, and `© OpenStreetMap contributors` attribution. The proxy identifies itself with the configured WxSpot User-Agent. Search results are cached for 30 days. A Postgres advisory lock and shared budget row enforce at most one uncached upstream search per second across API replicas; cached searches are served without contacting Nominatim. The UI submits on an explicit Search action and does not use autocomplete. This follows the [Nominatim usage policy](https://operations.osmfoundation.org/policies/nominatim/); re-evaluate the provider and global budget before materially increasing beta search volume.

## Nearby radar site inventory: NOAA Office for Coastal Management

`GET /weather/radar/stations/nearby` uses the NOAA OCM Weather Radar Stations FeatureServer catalog for station identifiers, names, and coordinates. It filters the catalog to NEXRAD identifiers, computes geodesic distance from the requested WGS84 point, and returns up to twelve nearest sites within 600 km. TDWR entries are intentionally excluded from this NEXRAD station picker. The catalog is cached in memory for 24 hours per API process; the response includes its fetch time. This inventory supplies station metadata only; the selected site's current product and scan availability still come from the RIDGE2 capabilities provider. An unavailable catalog is a typed source failure, not a fabricated or empty successful inventory.

## Other sources planned, not implemented

| Source | Format/cadence/retention | Consumption and constraints |
| --- | --- | --- |
| [NOAA NODD NEXRAD](https://www.noaa.gov/nodd/datasets) | Level II radar and broader archive options; volume cadence and archive retention vary | Later ingest selected Level II products, process to tiled rasters, retain stable volume/tilt IDs; budget CPU/storage and verify each distributor's terms. P2-04 Level III products are documented above. |
| [SPC](https://www.spc.noaa.gov/) | Outlooks/discussions/reports; event-driven updates | Later official vector/context layers; preserve source/issue/expiry and product-specific reuse conditions. |
| [AviationWeather API](https://aviationweather.gov/data/api/) | METAR observations; station cadence | Later observation adapter; retain report observation time, units, quality state and attribution. |

Planned sources are architectural capacity, not advertised app features. Their product-specific retention, redistribution rules, quotas, failure semantics, and processing costs must be verified at implementation.

### Decoder dependency validation

The Python ecCodes bindings 2.43.0 permit later native packages; ecCodeslib 2.49.0.30 with eckitlib 2.3.0.30 reproduced a pyproj import/shutdown crash. Pin ecCodeslib 2.43.0, eckitlib 1.32.4.11 and fckitlib 0.14.1.11; native imports and the six real Level III fixture tests exit cleanly with this set. MRMS uses the documented `codes_new_from_message` entry point. Regular-latitude/longitude first longitude is normalized to WGS84 before sampling.

## Phase 2 satellite

Operational GOES-East/West spacecraft IDs are discovered from the NOAA nowCOAST satellite WMS catalog. Raw ABI Cloud and Moisture Imagery CONUS objects come from NOAA's `noaa-goesNN` public S3 buckets. Frame IDs retain spacecraft, product and raw scan-start token. Valid time is the scan midpoint; scan start/end remain explicit. Required quantitative bands are C02 reflectance and C13/C08/C09/C10 brightness temperature. Decoder verifies platform, band, units and both timestamps, uses each file's geostationary projection/ellipsoid/sweep axes and masks DQF values above 1. Packed reflectance/temperature samples are converted only during geographic sampling. Visible imagery is dark at night.

GeoColor uses the official NOAA STAR/CIRA CONUS 2500x1500 derivative associated with the matching ABI scan. Only published composite filenames are advertised. Filename minute is the composite representative time; underlying ABI scan start/end are retained separately. Native fixed-grid alignment is retained; the embedded timestamp/footer and logo are masked. Static city lights/borders are disclosed. RGB composite has a descriptive legend rather than a quantitative temperature scale.

References: [NOAA CMIP metadata](https://www.ncei.noaa.gov/access/metadata/landing-page/bin/iso?id=gov.noaa.ncdc:C01502), [ABI CMIP algorithm](https://www.star.nesdis.noaa.gov/goesr/documents/ATBDs/Enterprise/ATBD_Enterprise_Cloud_and_Moisture_Imagery_Product_v5_2024-03-18.pdf), [STAR GeoColor](https://www.star.nesdis.noaa.gov/GOES/conus_band.php?band=GEOCOLOR&dim=1&length=36&sat=G19). Small unmodified-value NOAA C13 cutouts and independently evaluated temperature samples are recorded in `backend/tests/fixtures/goes/reference.json`; whole source-object hashes retain provenance. Live validation decodes all six products in both sectors and measures grid size/RSS/latency.

## Phase 2 model forecasts

Current operational buckets are `noaa-hrrr-bdp-pds` and `noaa-gfs-bdp-pds`, verified against the [NOAA HRRR registry](https://registry.opendata.aws/noaa-hrrr-pds/) and live objects. HRRR uses CONUS `wrfsfc` files; GFS uses `pgrb2.0p25` and retains the native 0.25-degree CONUS subset. [NCEP HRRR inventory](https://www.nco.ncep.noaa.gov/pmb/products/hrrr/) and [GFS inventory](https://www.nco.ncep.noaa.gov/pmb/products/gfs/) describe the published products. File and companion index inventories determine real run/hour availability; ordinary HRRR cycles end at F18, 00/06/12/18 extended cycles at F48. GFS is hourly F000–F120 then F123–F168 every three hours. Refresh preserves the selected run; latest run is an explicit bottom-sheet action.

Validated mappings: REFC/entire atmosphere (GRIB dB, forecast dBZ); TMP and DPT/2 m (K converted to Celsius); UGRD+VGRD/10 m and GUST/surface (m/s); APCP/surface (kg/m² = mm); CAPE and CIN/surface (J/kg); PWAT/entire atmosphere single layer (kg/m² = mm). Surface CAPE/CIN are not substituted with pressure-layer parcels. Decoder checks variable, level, run, hour, step units, statistics, geometry and physical units. Missing samples remain masked. HRRR winds with grid-relative flags are rotated by native Lambert convergence to east/north components; a separate geodesic-basis fixture verifies the rotation sign. Map barbs use meteorological wind-from direction. Tiles preserve native detail.

APCP selection reads actual start/end steps and accumulation statistics. Interval maps use the shortest published interval. Identical duplicate messages are verified by decoded values; conflicting duplicates fail. Run totals use a valid 0-to-hour accumulation or sum contiguous non-overlapping intervals from one run, preserving missing values and rejecting gaps/overlaps/negative inputs. Accumulation start/end remain explicit in metadata. GFS long totals exercise accumulation resets.

A single persistent codec subprocess isolates ecCodes native libraries from pyproj after a reproduced shutdown segfault when model geometry decoding loaded both native projection implementations. Framed input is capped at 16 MiB, decoded output at 32 MiB, grids at four million points, and each codec request at 45 seconds. Parent/worker processing remains bounded. Exact numeric field pointers are shared in Postgres/object storage under full model/run/hour/field/level/domain/processing keys. Live tests validate all ten fields for each model and a long actual run total.


## Implemented: forecast and observed soundings

Forecast columns use the exact HRRR/GFS run/hour and nearest native grid cell, with the sampled coordinates and distance disclosed. Pressure/temperature/moisture/height/east-north winds are decoded separately from surface map fields. Surface pressure and terrain mask underground levels; duplicate pressures and mismatched grids are rejected. HRRR grid-relative winds use the same independently checked rotation as model maps. The near-surface anchor uses 2 m thermodynamics and 10 m wind, explicitly labeled. GFS moisture can publish supersaturation: original dew points remain in the profile; diagnostic calculations limit Td to T and report that adjustment.

Observed profiles use [NOAA NCEI IGRA](https://www.ncei.noaa.gov/products/weather-balloon/integrated-global-radiosonde-archive), its station catalog and current-year station archives. Preserve QC flags, missing values, station metadata, actual release and nominal launch times. The newest available profile can lag the scheduled launch; show actual age instead of labeling it current. An observed launch is associated with its station, never manufactured for an arbitrary map point.

The globally bounded weather worker prepares profiles and separate [MetPy 1.7.1 diagnostics](https://unidata.github.io/MetPy/latest/api/generated/metpy.calc.html). Parcel settings are surface-based, a pressure-depth 100 hPa mixed layer and a lowest-300 hPa most-unstable layer. Report SB/ML/MU CAPE/CIN, selected parcel LCL/LFC/EL, PWAT, DCAPE, freezing/WBZ levels, vector shear, Bunkers right/left motion and SRH with the selected motion. Use MSL for source height and explicit AGL for wind layers. Unavailable diagnostics retain units and a reason; missing moisture is not replaced with zero or bridged across the thermodynamic profile. Parcel CAPE is distinct from the model's native surface CAPE map field.

Profile/diagnostic identities include the source run/launch, sampled point, processing version and calculation inputs. Parcel/motion changes reuse source profiles. Raw shared HRRR range caching is bounded to 512 entries/768 MiB; worker manifests/artifacts use the shared job retention. Reference cases include the published Norman MetPy sounding, stable/high-terrain/incomplete profiles and rotated winds. Native log-pressure/skew transforms and meteorological wind conventions have Android fixtures; real HRRR/GFS/IGRA sources and chart gestures passed PR #9.

## Implemented: NWS location weather

[NWS API documentation](https://www.weather.gov/documentation/services-web-api) defines `/points/{lat},{lon}`, forecast/forecastHourly/forecastGridData and observation station links. Resolve those links through point metadata; validate the NWS HTTPS host and allowed endpoint family before fetching. Do not forward device credentials. The adapter considers the three nearest stations and returns the nearest usable QC observation, with station coordinates, distance, observation time and age. It preserves null temperatures, dew points, winds, gusts and humidity; an observation older than 90 minutes is stale.

Return the next 48-hour window of available hourly periods and up to seven days of day/night forecast periods with source intervals, precipitation probability, numeric units and the original NWS narrative. Quantitative precipitation comes from grid valid-time intervals; preserve amount, start and end, including multi-hour intervals. Never divide a multi-hour amount into invented hourly totals. API values use Celsius, m/s and mm; the Android unit preference converts numeric displays consistently and labels the NWS narrative's original units.

Point metadata refreshes daily; station inventories hourly; observations every two minutes; forecast/grid documents every five minutes. Duplicate requests coalesce. Each document is limited to 2 MiB and 25 seconds, process cache to 64 entries, shared NWS cache to 128 entries/32 MiB and stale recovery to 12 hours. The four sections retain their own source/fetch/update times and ready/stale/no-data/error state. Successful sections remain visible during partial failure. Source absence or unsupported regions remain explicit; no forecast is substituted for a current observation. Live Summerville observation/forecast/interval checks and native saved-place/unit acceptance passed PR #10.
