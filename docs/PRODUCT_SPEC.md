# WxSpot: milestone 1

WxSpot teaches weather through geographically anchored community annotations. Android opens directly to a weather map; the feed is secondary. No account is needed to browse. Account actions prompt sign-in in context.

## Required interaction

Radar → scrub → long press → Mark this → Analysis, Observation, Question, or Photo/Report → geographic markup → explanation → publish. Another account opens the post, restores the camera/product/frame, advances the timeline, and returns to the marked frame. Moving weather never moves the annotation.

The workspace supports pin, ellipse, arrow, polyline, polygon, freehand, and text. Select/move, vertex resizing, undo/redo, delete, color, and thickness belong to the workspace. The short composer requires only description; title, topics, why-this-matters, and what-to-watch-next are optional.

Discovery defaults to ten recent posts in the viewport and last 24 hours. Filters cover type, topic, verified authors, Recent, Top, Following, and most-followed authors. Top combines engagement with time decay. Dense locations cluster. Feed selection restores the same map context.

Official NWS alerts occupy a separate layer and detail surface with provenance and expiration. Community analysis is always labeled community content. Self-declared profile roles never imply verification. No emergency push notification behavior is included.

## Social slice

Profiles, one like per user, people follows, top-level comments and one reply level, report, block, soft deletion, moderator removal with reason and audit record. In-app notifications are separate from official weather products. Future follow targets and explanation providers have explicit extension boundaries.

## Acceptance

Validate the supplied 20-step device workflow, including two authenticated sessions, exact replay, advancing at least one frame, unchanged coordinates, and return. Automated backend/PostGIS and Android domain tests supplement a device smoke test; a successful build alone is not device acceptance.

## Scope

Real NOAA reflectivity and radial velocity, NWS alerts, and social annotations. Satellite, models, subscriptions, advertisements, reputation scoring, AI interpretation, and direct Level-II processing are subsequent work. No production fallback to invented weather or development identities.
