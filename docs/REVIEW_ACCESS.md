# Review access without sign-in

Version 0.1.1 opens directly to the weather map. Posting, photo attachments, comments/replies, likes, follows, Following filters/feed, reports, blocks, deletion of your own content, and community notifications work without entering an email or password. The profile menu lets you change your display name and unblock people. There are no sign-in, registration, or sign-out controls in the Android UI.

Each installation receives a separate persistent device profile. Its private credential is stored encrypted with Android Keystore; the server stores a digest and uses the existing authentication library for normal bearer sessions. Session renewal preserves posts, likes, follows, and ownership. Simultaneous requests create one identity. Weather browsing can proceed while the community connection is being established. Weather sources, official warning provenance, geographic editing, and exact radar replay are unchanged.

Profile credentials survive normal restarts. Clearing application data or reinstalling creates a new profile; cross-device recovery/account linking is future work. A previously saved valid account session is retained when installing an update. Ordinary profiles cannot change verified roles, moderate other users' content, or read another profile's private block list.

## API

- `POST /auth/guest` with `{}` creates a profile and returns `access_token`, `token_type`, `resume_key`, `user_id`, and `display_name`.
- The same endpoint with `{"resume_key":"<device credential>"}` renews the session for that profile. An invalid or disabled credential returns 401; it never creates a replacement identity.
- `PATCH /account` with `{"display_name":"<name>"}` updates the caller's display name. Extra privilege fields are rejected.
- `GET /account/blocks` returns only people blocked by the caller. Existing `DELETE /profiles/{id}/block` unblocks a person.

The resume credential must stay out of URLs, logs, analytics, repository files, and screenshots. All account actions still use ordinary server authorization and posting quotas. The bootstrap endpoint uses the existing per-client authentication quota. Current email/password API routes remain available for other clients; the Android review experience does not use them.

## Verification

Backend tests cover separate device identities, hashed credential storage, renewal after actual session expiry, preserved ownership, disabled/invalid credentials, restricted privileges, full social actions, display-name persistence, and private block-list controls. Android tests cover concurrent bootstrap, saved-session reuse, renewal/retry, bounded retry, failed-resume ownership preservation, and credential isolation from external hosts.

The live device workflow launches without account forms, publishes real NOAA radar markup, opens it as a second automatically issued profile, restores and advances the weather context, returns to the marked frame, and likes/comments/follows/filters. It also checks actual NWS polygon rendering and separate official provenance. GitHub Actions runs backend/PostGIS integration, Android formatting/unit/lint/debug/release checks, and the live device workflow before integration.
