# Sounding implementation checkpoint

Updated 2026-10-08. P2-06 is merged and deployed. P2-07 implementation is now integrated; hosted acceptance remains pending.

Forecast HRRR/GFS columns use one native sample cell, immutable run/hour identity, terrain masks and earth-relative winds. Actual live extraction and source byte/request counts are recorded in PHASE2_STATUS.md. IGRA 2.2 parsing preserves actual release times, nominal times and QC/missing values. Latest observed inventories refresh hourly and expose their available releases; older data is shown with its age.

The existing globally bounded weather worker prepares profiles and separate parcel/motion diagnostics. HRRR pressure-field ranges use a shared expiring cache capped at 512 entries/768 MiB. One cell per field is retained during decoding. API requests only enqueue or read bounded prepared JSON documents. Explicit retry can reset exhausted jobs after a cooldown; ordinary polls preserve the finite retry cap.

Pinned MetPy 1.7.1 computes SB/ML100/MU300 CAPE/CIN, selected LCL/LFC/EL, DCAPE, PWAT, shear, Bunkers motions and chosen-motion SRH. Missing or inadequate layers return null with reasons. Guides, virtual buoyancy shading and parcel traces feed native charts. Tests use published MetPy references, an independently computed hodograph, stable/incomplete/high-terrain cases and observed QC records.

Native Android charts have true skew/log-pressure geometry, wind barbs, height-colored hodographs, marker drag for custom motion, level crosshair, pinch/pan and reset. Point selection, station/release selection, forecast-hour stepping and bottom parcel/motion controls are wired into the existing map shell. Selection generations cancel stale work.

Remaining: hosted PostGIS job round trip/cache-bound checks, Android lint/build, live forecast/observed smoke checks and native device gestures. Physical Pixel 8 Pro and signing continuity remain P2-10 checks.
