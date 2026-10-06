# Weather data sources

Verified 2026-10-06 against official documentation and a live KCLX capabilities response. Revalidate services before expanding products.

## Implemented: NOAA/NWS RIDGE2

Authority: [NWS radar FAQ](https://www.weather.gov/radarfaq), [NWS CloudGIS](https://www.weather.gov/gis/cloudgiswebservices), and [GeoServer directory](https://opengeo.ncep.noaa.gov/geoserver/www/index.html).

Endpoint: https://opengeo.ncep.noaa.gov/geoserver/{site}/ows. WMS GetCapabilities 1.3.0 supplies layer names and ISO8601 time dimensions. Implemented NEXRAD products are `{site}_sr_bref` and `{site}_sr_bvel`. GetMap uses WMS 1.1.1, EPSG:3857, an explicit TIME, transparent PNG, and longitude-safe projected bounding boxes. Scan cadence varies with radar operation; do not infer scans at uniform intervals. KCLX advertised 23 scans over roughly two hours at inspection. Parse the advertised frames, never manufacture timestamps. Single-site elevation is not advertised reliably and remains null, rather than assuming 0.5°.

Client consumes direct immutable-time WMS tiles while live. API caches capability metadata for 45 seconds and preserves a georeferenced 1024-pixel WMS raster at publication for replay. Display attribution “NOAA / National Weather Service.” No published request quota or availability SLA was found. Bound concurrency and timeouts; expect XML exceptions, delayed scans, missing sites/products, and time eviction. Check exact advertised membership before capturing because nearestValue can select a different frame. Data is public federal weather data; our service adds no claim of official endorsement.

NOAA GetLegendGraphic supplies the provider color scale; frame metadata and captured layer metadata retain its URL. Reflectivity reports dBZ. The velocity WMS capabilities and legend inspected do not unambiguously advertise physical units, so the slice labels the provider scale and never guesses m/s or knots. Elevation remains unspecified for the same reason.

## Implemented: official NWS alerts

Authority: [NWS API documentation](https://www.weather.gov/documentation/services-web-api) and https://api.weather.gov/openapi.json. `/alerts/active` returns GeoJSON with identifiers, event, severity, sent/effective/expiry, senderName, headline, and geometry. API uses a descriptive User-Agent, requests application/geo+json, and caches for 45 seconds. The documented rate limit is intentionally unpublished; obey upstream errors and retry later. Alerts change asynchronously; expiration is evaluated at display time. API alert history is seven days, not a complete archive. Some alerts lack polygon geometry; the API preserves those records with null geometry and the map renders only supplied polygons. Never fabricate geometry. Preserve official provenance and link to the source.

The alert layer always shows current alerts independently of the radar playback clock. Radar posts do not archive NWS warning history; the layer controls state that distinction. While the map is visible, a local check every ten seconds removes expired cached geometry and closes an expired detail, including during an outage or annotation editing. Returning to the map runs the check immediately. Geometry without a readable expiry is excluded from display.

## Basemap

OpenStreetMap standard raster tiles, WGS84/Web Mercator, with visible attribution and a descriptive client User-Agent. [OSM tile policy](https://operations.osmfoundation.org/policies/tiles/) requires attribution, caching, no bulk/offline prefetch, and reasonable use. This testing default must move to a production tile service or self-hosting before substantial public traffic. URLs/style are configurable. No automatic use of MapLibre demo infrastructure in production.

## Planned, not implemented

| Source | Format/cadence/retention | Consumption and constraints |
| --- | --- | --- |
| [NOAA NODD NEXRAD](https://www.noaa.gov/nodd/datasets) | Level II/III radar files; volume cadence and archive retention vary | Later ingest selected products, process to tiled rasters, retain stable volume/tilt IDs; budget CPU/storage and verify each distributor's terms. |
| [NOAA GOES via NODD](https://www.noaa.gov/nodd/datasets) | NetCDF imagery; cadence varies by scan sector | Later preprocess selected GeoColor/IR products; retain satellite/channel/time and actual bounds; outages and partial sectors must be explicit. |
| [NCEP NOMADS](https://nomads.ncep.noaa.gov/) | GRIB2 models; run/hour dependent; operational rolling retention | Later ingest HRRR/GFS parameters and levels; preserve run, forecast hour and valid time. Avoid repeatedly downloading entire models; verify current rate policies. |
| [SPC](https://www.spc.noaa.gov/) | Outlooks/discussions/reports; event-driven updates | Later official vector/context layers; preserve source/issue/expiry and product-specific reuse conditions. |
| [AviationWeather API](https://aviationweather.gov/data/api/) | METAR observations; station cadence | Later observation adapter; retain report observation time, units, quality state and attribution. |

Planned sources are architectural capacity, not advertised app features. Their product-specific retention, redistribution rules, quotas, failure semantics, and processing costs must be verified at implementation.
