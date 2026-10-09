# Sounding Hunt data source and provenance

## Primary source

The game uses NOAA/NCEI **Integrated Global Radiosonde Archive (IGRA) version 2.2**, an archive of observed upper-air launches. Official product information: <https://www.ncei.noaa.gov/products/weather-balloon/integrated-global-radiosonde-archive>.

This mode uses radiosonde observations only. Forecast-model and reanalysis profiles are not eligible.

## Acquisition and parsing

The existing provider fetches the official station inventory and bounded individual station archive over HTTPS. The Sounding Hunt worker considers only verified CONUS station state codes and coordinates, caps one maintenance batch at three station archives, bounds an archive download to 16 MiB and an expanded archive member to 64 MiB, and records failed attempts/rejection reasons. An upstream fetch is never done in the player's request path.

The existing IGRA parser reads the documented fixed-width station/launch/level records and retains up to the newest 32 launches per bounded station archive. It handles missing (`-9999`) and QC-removed (`-8888`) values, temperature in tenths of degrees Celsius, pressure in pascals converted to hPa, wind speed in tenths of m/s, and wind direction converted to earth-relative u/v. Dew point temperature is computed from temperature minus the documented dew point depression; a valid relative-humidity fallback is used only where dew point depression is unavailable. Missing values remain null. Each launch is validated and stored independently, leaving unqueued verified profiles available for practice while daily challenges are active.

## Candidate quality

Profiles need 12 or more usable pressure levels, 10 or more measured temperatures, 6 or more measured dew points, coverage to at least 500 hPa, plausible pressure, ordered unique pressure levels, and a CONUS location. Four or more wind levels and standard 00Z/12Z observations are preferred, not synthesized as requirements. Candidate validation summaries and rejection reasons are retained for review.

The worker publishes unused validated observations into an approximately 14-day queue, avoids the same station within 30 days when possible, favors regional/launch-time variety, and only publishes existing verified observations. When NOAA is unavailable, the worker uses the queued observations and retries later; it does not generate synthetic data.

## Stored provenance

Private records retain source/provider and dataset version, source station identifier, observation and nominal launch times, station coordinates/elevation, validation details, ingestion time, and a SHA-256 revision of the downloaded station archive. The result screen displays source name/version and actual launch time only after reveal. The public pre-guess response omits station identity, coordinates, elevation, source revision, and source URLs.
