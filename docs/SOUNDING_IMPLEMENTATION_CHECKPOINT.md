# P2-07 sounding implementation checkpoint

This branch is unfinished and must not be merged or advertised as a working sounding feature. The workspace execution service became unavailable on October 8, 2026 (`environment_offline: Environment is not connected`). The source adapters and contracts are preserved here for continuation. Formatting, parsing tests, full live-profile validation, calculation jobs, API wiring and native interactive charts remain.

## Verified source investigation

- Official HRRR pressure inventory on October 7, 21 UTC F03 contains HGT, TMP, DPT, RH, SPFH, UGRD and VGRD on 39 levels from 1000 to 50 hPa, at 25 hPa spacing. Surface pressure/terrain and 2 m thermodynamics/10 m winds are in the surface file.
- GFS October 7, 18 UTC F03 has HGT/TMP/RH/SPFH/u/v pressure fields. Direct pressure-level DPT is absent. Derive dew point with pinned MetPy from verified RH; preserve null when humidity is missing.
- A real GFS NOMADS geographic subset around Charleston downloaded 52,668 bytes and decoded 288 messages on 2x2 grids (the investigation used all levels). Pressure HGT units are gpm; surface orography is metres. Pressure levels >=50 hPa decode as isobaricInhPa; the very high atmosphere may use isobaricInPa and is outside this initial subset.
- HRRR's documented NOMADS 2D filter advertises surface files. Attempting a pressure file returned HTTP 500. The checkpoint uses exact ranged pressure messages from NOAA's public HRRR S3 archive instead.
- The actual IGRA recent filename is `USM00072208-data-beg2026.txt.zip`, not `USM00072208-data.txt.zip`. The successful download was 3,956,938 bytes; its one ASCII member was 11,196,472 bytes.
- Official Charleston station: USM00072208, 32.8950 N, -80.0275 E, elevation 13.3 m. The retrieved archive's latest usable launch was October 7 at 11:04 UTC (nominal 12 UTC), with 330 reported levels. Observed launch age must be shown honestly.
- IGRA header times: nominal at columns 25–26, actual release HHMM at 28–31. A 23xx launch paired with next-day 00 UTC nominal time belongs to the prior UTC date. Missing release minutes/times need explicit quality labels.
- IGRA data pressure is Pa/100; temperature/dewpoint depression in tenths C; RH in tenths percent; wind speed in tenths m/s and meteorological wind-from direction. -9999 is missing, -8888 is QC removed. P/Z/T flags A/B indicate climatology checking, not fabricated error bars.

## Files and bounds

- `sounding_contracts.py`: explicit forecast/observed identities, units, real levels and nullable diagnostic contracts.
- `providers/soundings.py`: nearest consistent forecast column, terrain masking, earth-relative winds, GFS geographic subsets, HRRR ranged pressure fields, IGRA station/launch parsing and quality flags.
- `providers/model_grids.py`: pressure/surface pressure/terrain unit and level validation added to existing GRIB decoding.
- HRRR: <=39 pressure levels, <=210 messages, <=384 MiB ranged transfer, three bounded downloads at a time, one existing codec/CPU worker, retain only one cell per field.
- GFS: <=8 MiB subset response, <=350 GRIB messages, <=2048 grid points per message.
- IGRA: <=16 MiB compressed, <=64 MiB member, <=1500 levels per launch, retain 16 launches for at most eight stations; one-hour inventory refresh.
- Actual full-profile latency, input/output bytes, CPU, codec+parent peak memory and adequate pressure/wind coverage still need measurement. Adjust bounds only with recorded evidence.

## Next implementation

1. Sync model PR #8's final head/main merge. Inspect local files before overwriting them; scratch may contain the original contract and an unconfirmed provider patch.
2. Format and test these adapters. Record real HRRR/GFS/observed fixtures with independent values, high-terrain masking and rotation references.
3. Add profile jobs to the existing globally bounded weather worker, shared immutable profile artifacts, and separate derived-diagnostic jobs. Latest observed inventory requests need a refresh bucket; an immutable explicit launch must stay stable.
4. Add unit-aware MetPy SB, ML100, MU300 CAPE/CIN; selected LCL/LFC/EL with log-pressure height interpolation; DCAPE; bounded profile PWAT; 0–1/3/6 km vector shear; chosen RM/LM/custom SRH; Bunkers and 0–6 km mean wind. Missing moisture/layer extent must return null with a reason. ML parcel must average potential temperature and mixing ratio, not dew point.
5. Use official MetPy numerical examples plus independently calculated shear/SRH cases. Require sufficient near-surface/upper-layer coverage; disclose the 10 m forecast wind anchor. Do not extrapolate below terrain.
6. Implement native interactive Skew-T/log-pressure transforms, moist/dry/mixing guides, barbs, parcel trace, buoyancy shading and markers; height-colored hodograph with motion marker; pinch zoom/pan/crosshair/reset; bottom parcel/motion/run/hour/launch controls. Parcel/motion changes must reuse the same profile and reject stale responses.
7. Continue P2-08 location conditions/forecasts, P2-09 cross-source replay audit, P2-10 lifecycle/performance/signing/APK release. Do not claim a Pixel 8 Pro test without access to that physical device. Original review-key continuity is unresolved.

## Primary source URLs

- https://nomads.ncep.noaa.gov/
- https://www.cpc.ncep.noaa.gov/products/tools/scripting_grib_filter.html
- https://noaa-hrrr-bdp-pds.s3.amazonaws.com/
- https://noaa-gfs-bdp-pds.s3.amazonaws.com/
- https://www.ncei.noaa.gov/pub/data/igra/igra2-data-format.txt
- https://www.ncei.noaa.gov/pub/data/igra/igra2-station-list.txt
- https://www.ncei.noaa.gov/pub/data/igra/data/data-y2d/
- https://unidata.github.io/MetPy/latest/api/generated/metpy.calc.mixed_parcel.html
- https://unidata.github.io/MetPy/latest/api/generated/metpy.calc.cape_cin.html
- https://unidata.github.io/MetPy/latest/api/generated/metpy.calc.downdraft_cape.html
- https://unidata.github.io/MetPy/latest/api/generated/metpy.calc.bunkers_storm_motion.html
- https://unidata.github.io/MetPy/latest/api/generated/metpy.calc.storm_relative_helicity.html
