# API contract

FastAPI serves the current OpenAPI contract at `/openapi.json`, with interactive documentation at `/docs`. Community record IDs are UUIDs, timestamps contain an explicit UTC offset, and coordinates use `[longitude, latitude]` in WGS84. Weather frame IDs are opaque and must come from the frame catalog.

| Capability | Endpoint | Access |
| --- | --- | --- |
| Automatic device profile/renewal | `POST /auth/guest` with `{}` or saved `resume_key` | Public bootstrap; bounded and revocable |
| Profile name and private blocks | `PATCH /account`, `GET /account/blocks` | Authenticated |
| Compatibility register; sign in; revoke session | `POST /auth/register`, `/auth/login`, `/auth/logout` | Registration/login public; logout authenticated |
| Private account identity | `GET /account` | Authenticated |
| Live NOAA scans and source state | `GET /weather/radar/frames?site=KCLX&product=reflectivity` | Public |
| Verified weather products | `GET /weather/catalog` | Public; short-lived cache |
| Source-aware weather frames | `GET /weather/frames?source_type=radar&source_id=nws-ridge2&product=reflectivity&site=KCLX` | Public; short-lived cache |
| Shared heavy-weather preparation | `GET /weather/prepare?source_type=model&source_id=noaa-models&frame_id=...` | Public; bounded/coalesced worker jobs |
| Immutable scientific tiles and legends | `GET /weather/render/tile/{z}/{x}/{y}.png`, `/weather/render/legend/{source_id}/{product}.png` | Public; validated frame identity |
| Forecast/observed soundings | `GET /weather/soundings`, `/weather/soundings/stations?lat=33&lon=-80` | Public; source/diagnostic jobs and typed states |
| Location observations and forecasts | `GET /weather/locations/forecast?lat=33&lon=-80` | Public; independent section freshness |
| Explicit place search | `GET /weather/locations/search?q=Charleston&lat=33&lon=-80` | Public; cached results, shared upstream request budget |
| Nearby NEXRAD sites | `GET /weather/radar/stations/nearby?lat=33&lon=-80` | Public; short-lived cache |
| Dedicated official NWS alerts | `GET /weather/alerts` | Public |
| Attributed MapLibre basemap style | `GET /weather/style` | Public |
| Discover spatially | `GET /posts?bbox=west,south,east,north&sort=recent&limit=10` | Public; Following requires identity |
| Publish; open; soft-delete | `POST /posts`, `GET /posts/{id}`, `DELETE /posts/{id}` | Publish authenticated; delete author only |
| Exact preserved weather layer | `GET /posts/{id}/archives/{layer_id}` | Same visibility as post |
| Like/unlike | `PUT` / `DELETE /posts/{id}/like` | Authenticated; idempotent |
| Comments and one reply level | `GET` / `POST /posts/{id}/comments`, `DELETE /comments/{id}` | Read public; write authenticated; delete author only |
| Public profile; follow/unfollow | `GET /profiles/{id}`, `PUT` / `DELETE /profiles/{id}/follow` | Profile public; follows authenticated |
| Block/unblock | `PUT` / `DELETE /profiles/{id}/block` | Authenticated |
| Photos | `POST /media`, `GET /media/{id}` | Upload authenticated; attached media follows post visibility |
| Report; review; moderate | `POST /reports`, `GET /moderation/reports`, `POST /moderation/actions` | Reports authenticated; moderation restricted |
| Community notifications | `GET /notifications`, `PUT /notifications/{id}/read` | Recipient only |
| Database/PostGIS readiness | `GET /health` | Public |

Discovery defaults to the last 24 hours and ten posts. `hours` accepts 1–168; `limit` accepts 1–50. Optional filters: `content_type`, `topic`, `verified_only`. Sorts: `recent`, `top`, `following`, `most_followed`. Recent and Following have stable `(created_at, id)` cursors. Top and Most-followed return a bounded ranked set because ranking changes over time. Antimeridian-crossing discovery boxes are split into two indexed spatial predicates. Publishing currently requires a non-crossing captured viewport.

Top score is `(likes + 0.5 × active comments + 1) / (age_hours + 2)^1.5`. Spatial predicates use the PostGIS GiST footprint index. Serialization batches counts, media, liked status, and followed authors across a page rather than issuing those queries separately for every post.

Publishing validates the complete context and tool geometry, verifies exact source identity against provider inventory and raw metadata, preserves the raw georeferenced weather raster in object storage, then commits context, geographic elements, media associations, and follower notifications. A capture failure returns an explicit error; Android retains its draft. This is a weather raster archive, separate from editable vector annotations and the original camera/product/time metadata.

Weather responses distinguish `ready`, `preparing`, `source_delayed`, `no_data`, `unsupported_product`, `source_unavailable`, and `render_error`; Android also distinguishes network and image loading failures. Upstream failure never generates a replacement scan. The v1 `/weather/radar/frames` endpoint remains available to older builds. The generic `/weather/catalog` and `/weather/frames` endpoints use explicit source/product IDs and namespaced frame IDs; `render` describes the exact XYZ template or image, and unknown coverage remains null. The catalog includes verified RIDGE2, MRMS, NEXRAD Level III, GOES East/West and HRRR/GFS products. The generic API does not advertise unimplemented feeds.

`GET /weather/locations/search` accepts an explicitly submitted `q` of 3–120 characters and optional WGS84 `lat`/`lon` search bias. The response has `state` (`ready`, `no_results`, `busy`, or `source_unavailable`), bounded canonical result names and coordinates, attribution, and an optional retry hint. The server normalizes and caches searches for 30 days and coordinates a one-request-per-second Nominatim limit across API replicas with a Postgres advisory lock and singleton budget row. Cached results do not consume the upstream request budget. The public geocoder is called only after a user submits a search; the API does not expose autocomplete. Search requests use the configured descriptive User-Agent and never forward the device-profile bearer token to OpenStreetMap.

`GET /weather/radar/stations/nearby` requires a point and returns the nearest usable NEXRAD station records from NOAA's station inventory, ordered by distance and limited to sites within 600 km. The server caches the provider inventory for 24 hours per process; the response exposes inventory freshness. TDWR entries and malformed/non-NEXRAD identifiers are excluded from this NEXRAD picker. A temporary provider error is returned as the explicit `source_unavailable` state rather than as an empty successful list.

Saved places, their order, the last map camera, and the metric-units preference are device-local Android preferences. They are not tied to the anonymous community profile and require no sign-in or cloud synchronization. The store accepts up to 100 places with stable local UUIDs and validates names and WGS84 coordinates. Location permission is requested only when the foreground GPS action is tapped; Android requests coarse/fine foreground permissions and no background-location permission. Search and saved-place selection remain available after denial.

`WeatherSelection`, `WeatherFrame`, `WeatherFramesResponse`, and `WeatherProduct` are versioned source-neutral contracts. Each frame is tied to one provider, product, and valid time; model frame validation requires `valid_time = run_time + forecast_hour`. Frames in one response share their source and product and are ordered by valid time. Both generic weather endpoints are public and use bounded freshness headers; published layer archives retain their existing post visibility and authorization rules.

Publishing dispatches through the `(source_type, provider)` registry. RIDGE2 accepts the original v1 radar frame IDs and namespaced generic IDs, then regenerates its server-side WMS URL from validated site/product/time fields. It never downloads a client-supplied URL. New weather archives use `weather/{post_id}/{layer_id}.png`; existing archive keys and old v1 posts remain readable.

Revocable bearer tokens expire after seven days. Password handling is supplied by FastAPI Users. Public profiles exclude email and authentication flags. Verified role and moderator privileges are never self-service registration fields. Blocking suppresses visibility and interaction in both directions; ordinary deletion preserves evidence. Moderation changes retain actor, reason, previous/new status, and UTC audit time.


`GET /weather/soundings` takes `kind=forecast|observed`, WGS84 `lat`/`lon`, `parcel=sb|ml100|mu300`, and `motion=rm|lm|custom`. Forecast requests require `model=hrrr|gfs`, `domain=conus`, an explicit offset-aware `run_time` and real `forecast_hour` (HRRR F18/F48 by cycle; GFS F168 with three-hour cadence beyond F120). Observed requests require an 11-character IGRA station ID and may pin an offset-aware `launch`; omission selects the latest available release and reports its actual time. Custom motion requires east/north `storm_u` and `storm_v` in m/s. `retry_failed=true` explicitly requeues eligible failed jobs.

The sounding response has `state`, `requested_point`, sampled distance, optional real `profile`, optional `diagnostics`, source options and `retry_after_seconds`. `preparing` responses can already contain the profile while diagnostics are pending. Profile levels use strictly descending unique hPa, nullable Celsius dew point/temperature, MSL height and earth-relative m/s winds. Diagnostic values carry units/method/reason and parcel/motion identity, with traces/markers/guide coordinates for native plots. A new parcel or motion creates a derived job while retaining the immutable source profile. HTTP freshness is three seconds; station metadata is cached for an hour.

`GET /weather/locations/forecast` requires a WGS84 point and returns NWS timezone/place/grid metadata plus `observation`, `hourly`, `daily` and `amounts` sections. Each section reports ready/stale/no-data/source-unavailable separately, with source URL, fetch/update times, nullable values and actual period boundaries. Observations report station/time/age/distance; rainfall reports start/end/mm rather than invented hourly amounts. Aggregate state can be partial. Numeric API units are Celsius, m/s and mm. HTTP freshness is 60 seconds with 120-second stale-while-revalidate; individual upstream caches have independent bounded lifetimes.

Protected post archives return `Cache-Control: private, no-store` and `Vary: Authorization`; Android archive requests also prohibit HTTP cache reuse. Every load evaluates current post visibility and block status. Published archives survive live object expiry/cleanup. Those access rules differ from publicly cacheable immutable weather tiles.

The Android application uses automatic device profiles without account forms. Saved resume credentials remain encrypted locally, renew the existing identity, and never travel to weather providers. A failed renewal retains the local identity for retry rather than silently creating a new profile. See REVIEW_ACCESS.md and BETA_ACCEPTANCE.md for reset and signing-transition semantics.
