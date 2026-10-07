# API contract

FastAPI serves the current OpenAPI contract at `/openapi.json`, with interactive documentation at `/docs`. All public IDs are UUIDs, timestamps contain an explicit UTC offset, and coordinates use `[longitude, latitude]` in WGS84. Weather frame IDs are opaque and must come from the frame catalog.

| Capability | Endpoint | Access |
| --- | --- | --- |
| Register; sign in; revoke session | `POST /auth/register`, `/auth/login`, `/auth/logout` | Registration/login public; logout authenticated |
| Private account identity | `GET /account` | Authenticated |
| Live NOAA scans and source state | `GET /weather/radar/frames?site=KCLX&product=reflectivity` | Public |
| Verified weather products | `GET /weather/catalog` | Public; short-lived cache |
| Source-aware weather frames | `GET /weather/frames?source_type=radar&source_id=nws-ridge2&product=reflectivity&site=KCLX` | Public; short-lived cache |
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

Publishing validates the complete context and tool geometry, verifies exact scan identity against fresh NOAA capabilities, preserves the raw georeferenced weather raster in object storage, then commits context, geographic elements, media associations, and follower notifications. A capture failure returns an explicit error; Android retains its draft. This is a weather raster archive, separate from editable vector annotations and the original camera/product/time metadata.

Weather responses distinguish `ready`, `preparing`, `source_delayed`, `no_data`, `unsupported_product`, `source_unavailable`, and `render_error`; Android also distinguishes network and image loading failures. Upstream failure never generates a replacement scan. The v1 `/weather/radar/frames` endpoint remains available to older builds. The generic `/weather/catalog` and `/weather/frames` endpoints use explicit source/product IDs and namespaced frame IDs; `render` describes the exact XYZ template or image, and unknown coverage remains null. Current catalog contents are limited to products exposed by the verified RIDGE2 adapter. The generic API does not advertise unimplemented feeds.

`WeatherSelection`, `WeatherFrame`, `WeatherFramesResponse`, and `WeatherProduct` are versioned source-neutral contracts. Each frame is tied to one provider, product, and valid time; model frame validation requires `valid_time = run_time + forecast_hour`. Frames in one response share their source and product and are ordered by valid time. Both generic weather endpoints are public and use bounded freshness headers; published layer archives retain their existing post visibility and authorization rules.

Publishing dispatches through the `(source_type, provider)` registry. RIDGE2 accepts the original v1 radar frame IDs and namespaced generic IDs, then regenerates its server-side WMS URL from validated site/product/time fields. It never downloads a client-supplied URL. New weather archives use `weather/{post_id}/{layer_id}.png`; existing archive keys and old v1 posts remain readable.

Revocable bearer tokens expire after seven days. Password handling is supplied by FastAPI Users. Public profiles exclude email and authentication flags. Verified role and moderator privileges are never self-service registration fields. Blocking suppresses visibility and interaction in both directions; ordinary deletion preserves evidence. Moderation changes retain actor, reason, previous/new status, and UTC audit time.
