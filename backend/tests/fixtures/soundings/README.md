# Sounding provenance

`../sounding_reference.txt` is Unidata MetPy's BSD-licensed `20110522_OUN_12Z.txt`
at tag `v1.7.1`, blob `bde30fa95f5f9c16311e22b88c34d7c1b3543159`.
The official Sounding Calculation Examples publishes independent Norman CAPE,
CIN, LCL/LFC/EL and Bunkers references. Tests compare those numbers with declared
numerical tolerances and separately compare shear/SRH with a hodograph computed
by hand. Stable, incomplete and high-terrain cases check missing-data behavior.

- https://github.com/Unidata/MetPy/blob/v1.7.1/staticdata/20110522_OUN_12Z.txt
- https://unidata.github.io/MetPy/latest/examples/calculations/Sounding_Calculations.html
- https://github.com/Unidata/MetPy/blob/v1.7.1/LICENSE

The HRRR/GFS JSON files preserve actual NOAA extracted columns sampled near
33.02 N, 80.18 W on 2026-10-08. Their run/hour, sampled coordinates, level quality,
origin requests and byte counts are embedded in each profile. They are source
samples, not independent expected calculation values. HRRR uses exact range
requests from the pressure and surface files; GFS uses a bounded NOMADS subset.

- https://noaa-hrrr-bdp-pds.s3.amazonaws.com/
- https://noaa-gfs-bdp-pds.s3.amazonaws.com/
- https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl
- https://www.ncei.noaa.gov/pub/data/igra/igra2-data-format.txt

Forecast profiles exclude below-ground isobaric levels, rotate HRRR winds to
earth east/north and disclose the 2 m thermodynamic/10 m wind surface anchor.
Published supersaturation is retained and flagged; calculations explicitly cap
dew point to temperature. Observed release times and QC-removed/missing values
are preserved. The observed inventory may lag current launches; the UI shows
the actual release time and age.
