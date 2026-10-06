# Data model

Public keys are UUIDs. All times are UTC. Geographic coordinates are WGS84 longitude/latitude; projected coordinates only appear in raster requests.

| Entity | Storage and invariants |
| --- | --- |
| User | FastAPI Users credential fields plus display name, self-declared role, separate verified role, moderator flag, created time. Sensitive credential/email fields never appear in public profiles. |
| AccessToken | Library-generated revocable database session with user FK and creation time. |
| WeatherPost | Author, type, description, optional educational fields/topics, creation/update/status/moderation reason, footprint GeometryCollection SRID 4326 + GiST. |
| WeatherContext | Versioned JSONB associated 1:1 with post, UTC valid time, camera, bounds, list of configured weather layers. Layer metadata admits radar/model/satellite identifiers. |
| AnnotationElement | Post FK, ordered UUID element, validated tool, GeoJSON point/line/polygon, stroke/color/label. Multiple elements per post. |
| LayerArchive | Post/layer, object key, original time/frame, geographic bounds. Raster contains no marks. |
| Comment | Post/author, optional parent in same post, at most one reply level, content status/timestamps. |
| Like | Unique post/user pair, no duplicate likes. |
| Follow | Unique follower/target type/target ID; V1 people, extensible area/topic/event targets. No self-follow. |
| Block | Unique blocker/blocked pair; bidirectional discovery/detail/discussion filtering. |
| Report | Reporter, post/comment target, reason, status, time. Ordinary deletion preserves reported evidence. |
| ModerationAction | Moderator, target, prior/new status, reason, timestamp. |
| Notification | Recipient/actor/type/post/comment/read time; community-only. No emergency-alert semantics. |
| PostingQuota | Actor/action/minute bucket count with atomic upsert; limits survive process restarts. |
| WeatherAlert | Provider response object/cache independent of community domain. Preserve official ID, geometry, issuing office, event, severity, issued/expires, provenance. |

Post index dimensions: spatial footprint, creation+ID for cursor pages, status+creation, author+creation, type+creation, JSONB topic tags. Viewport queries constrain time and status before returning a bounded result. Cursor is a stable time/UUID pair for recent feed pagination; ranked discovery is a bounded viewport result, not an all-records feed.

Geometry validation rejects non-finite or out-of-range coordinates, invalid polygons, and mismatched tool types. Ellipses are polygonized geographic shapes; arrows carry line geometry; text carries a point and label. Persisted elements never depend on screen dimensions.
