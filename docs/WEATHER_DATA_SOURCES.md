# Weather data sources

Verified 2026-10-06 against official documentation and a live KCLX capabilities response. Revalidate services before expanding products.

## Implemented: NOAA/NWS RIDGE2

Authority: [NWS radar FAQ](https://www.weather.gov/radarfaq), [NWS CloudGIS](https://www.weather.gov/gis/cloudgiswebservices), and [GeoServer directory](https://opengeo.ncep.noaa.gov/geoserver/www/index.html).

Endpoint: https://opengeo.ncep.noaa.gov/geoserver/{site}/ows. WMS GetCapabilities 1.3.0 supplies layer names and ISO8601 time dimensions. Implemented NEXRAD products are `{site}_sr_bref` and `{site}_sr_bvel`. GetMap uses WMS 1.1.1, EPSG:3857, an explicit TIME, transparent PNG, and longitude-safe projected bounding boxes. Scan cadence varies with radar operation; do not infer scans at uniform intervals. KCLX advertised 23 scans over roughly two hours at inspection. Parse the advertised frames, never manufacture timestamps. Single-site elevation is not advertised reliably and remains null, rather than assuming 0.5°.

Client consumes direct immutable-time WMS tiles while live. API caches capability metadata for 45 seconds and preserves a georeferenced 1024-pixel WMS raster at publication for replay. Display attribution “NOAA / National Weather Service.” No published request quota or availability SLA was found. Bound concurrency and timeouts; expect XML exceptions, delayed scans, missing sites/products, and time eviction. Check exact advertised membership before capturing because nearestValue can select a different frame. Data is public federal weather data; our service adds no claim of official endorsement.

The Phase 2 registry currently wraps only this existing provider. Its verified catalog exposes reflectivity in dBZ and base radial velocity with the provider's scale, not physical m/s. It does not claim nationwide coverage, numeric coverage bounds, or a fixed elevation. Generic frame IDs include source type and provider before the preserved v1 site/product/time identity; capture accepts both identity forms and regenerates the source URL from validated fields. `/weather/radar/frames` remains the compatibility contract for existing builds.

NOAA GetLegendGraphic supplies the provider color scale; frame metadata and captured layer metadata retain its URL. Reflectivity reports dBZ. The velocity WMS capabilities and legend inspected do not unambiguously advertise physical units, so the slice labels the provider scale and never guesses m/s or knots. Elevation remains unspecified for the same reason.

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
| [NOAA NODD NEXRAD](https://www.noaa.gov/nodd/datasets) | Level II/III radar files; volume cadence and archive retention vary | Later ingest selected products, process to tiled rasters, retain stable volume/tilt IDs; budget CPU/storage and verify each distributor's terms. |
| [NOAA GOES via NODD](https://www.noaa.gov/nodd/datasets) | NetCDF imagery; cadence varies by scan sector | Later preprocess selected GeoColor/IR products; retain satellite/channel/time and actual bounds; outages and partial sectors must be explicit. |
| [NCEP NOMADS](https://nomads.ncep.noaa.gov/) | GRIB2 models; run/hour dependent; operational rolling retention | Later ingest HRRR/GFS parameters and levels; preserve run, forecast hour and valid time. Avoid repeatedly downloading entire models; verify current rate policies. |
| [SPC](https://www.spc.noaa.gov/) | Outlooks/discussions/reports; event-driven updates | Later official vector/context layers; preserve source/issue/expiry and product-specific reuse conditions. |
| [AviationWeather API](https://aviationweather.gov/data/api/) | METAR observations; station cadence | Later observation adapter; retain report observation time, units, quality state and attribution. |

Planned sources are architectural capacity, not advertised app features. Their product-specific retention, redistribution rules, quotas, failure semantics, and processing costs must be verified at implementation.
