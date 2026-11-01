# Data sources

## Open-Meteo forecast

Official references: [forecast parameters](https://open-meteo.com/en/docs), [terms and limits](https://open-meteo.com/en/terms), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

The client calls `https://api.open-meteo.com/v1/forecast` with caller latitude/longitude, `forecast_days=14`, `timezone=UTC`, `timeformat=unixtime`, Celsius, millimetres and km/h. Hourly fields are temperature_2m, precipitation, et0_fao_evapotranspiration, soil_moisture_0_to_1cm and wind_speed_10m. Daily fields are temperature_2m_max, temperature_2m_min, precipitation_sum and et0_fao_evapotranspiration. Each timestamp is parsed as UTC. Tasks explicitly use UTC forecast days; these daily sums are not Indian local-day totals.

Responses preserve requested and resolved model-grid coordinates separately. Fetch time is reception time, not model issue time. Values may be null and remain null. Units and time-series alignment are validated. Data is model output, not a measurement from the plot. ET0 is reference evapotranspiration, not crop-specific irrigation demand.

The free service is restricted to non-commercial use and publishes limits below 600 requests/minute, 5,000/hour and 10,000/day. Recheck terms before deployment. Attribution accompanies every result. Cache freshness is an application policy (15 minutes fresh, up to one additional hour stale), not an upstream update guarantee. Stale data preserves the original fetch time; after the stale window, refresh failure raises a typed error. The CLI and web views preserve nulls, explicit stale flags and readable errors.

The transport retries network failures, HTTP 429 and server errors with bounded jitter. Authentication and validation failures are not retried. Each source has its own transport instance and circuit state. A malformed forecast marks source health degraded; successful HTTP alone does not make invalid data usable. Cache and circuit state are process-local. A cache must be closed before its HTTP client. Additional clients and their observed coverage are described below.

## Previous Runs decision

The [official Previous Runs documentation](https://open-meteo.com/en/docs/previous-runs-api) specifies fixed lead-time hourly values with `_previous_day1` through `_previous_day7`, corresponding to 24 through 168 hours before valid time. Use this API for the later backtest instead of a seamless historical forecast series. Most model archives begin in January 2024, with exceptions. The implemented backtest verifies seven GFS Global leads against ERA5 with explicit hourly/day coverage and unavailable Brier scores; see BACKTEST.md.

## Remaining sources

Live verification in this slice returned 14 daily and 336 hourly forecast entries through the implemented Python CLI. A separate request to `https://previous-runs-api.open-meteo.com/v1/forecast` used the same caller coordinates, `hourly=temperature_2m_previous_day1,precipitation_previous_day1`, `past_days=2`, `forecast_days=1`, `timezone=UTC`; it returned 72 non-null entries for each requested variable. This confirms endpoint availability for a short window, not completeness over a 60-day window. The implemented 60-day comparison and its actual boundary gap are documented in BACKTEST.md.

The ERA5 archive adapter supports backtests and the separate 1991–2020 historical chart baseline. Geocoding, flood, NASA POWER, SoilGrids and the key-gated Agmarknet adapter are described below, including observed gaps and unverified authenticated market behavior. No substitute prices, soil properties or observations are provided.

## Terms and response schema

Checked on 2026-10-30 by opening the official [home](https://open-meteo.com/), [terms](https://open-meteo.com/en/terms), [pricing](https://open-meteo.com/en/pricing), [licence](https://open-meteo.com/en/licence) and [forecast documentation](https://open-meteo.com/en/docs) pages.

The terms restrict the free API to non-commercial purposes and say less than 10,000 calls/day, 5,000/hour and 600/minute. Pricing additionally lists 300,000 calls/month. Its FAQ says monthly limits are not enforced until a usage portal is available; treat the published budget as the limit regardless. Shared hosting can encounter earlier IP-based throttling. The pricing page describes free access for evaluation and prototyping; commercial use needs a subscription. The free endpoint needs no authentication; commercial customer endpoints require an API key. Do not confuse the data licence, which permits redistribution and adaptation, with permission to use the hosted free API commercially.

Data licence: CC BY 4.0. The licence page requires credit, a licence link, indication of modifications and a link beside every display of the data. Its example credit is Weather data by Open-Meteo.com, linked to https://open-meteo.com/. The source envelope now carries attribution_text, attribution_url, licence_url and modifications for future UI rendering. No specific mandatory typography is stated. The server code's AGPL licence is distinct from the API data licence.

Parameter comparison found no mismatch: latitude/longitude are WGS84 floats; hourly/daily are comma-separated variables; 14 forecast days is within 0-16; daily requests include the required timezone. celsius, kmh, mm and unixtime are documented values. UTC means zero offset; returned GMT is the equivalent source label. Response latitude/longitude refer to the grid cell; hourly/daily time arrays and adjacent units dictionaries match the parser. Temperature is degrees Celsius, precipitation and ET0 are millimetres, wind is km/h, soil water content is m³/m³. Hourly precipitation and ET0 cover the preceding hour; temperatures, soil moisture and wind are instantaneous. Daily values aggregate UTC days. Local-day advice remains deferred. Numeric values are not altered; timestamps and response structure are transformed as disclosed.

Source failures use an error envelope containing code, message, source, retryable and request_id. Network errors read Open-Meteo forecast: network error (retryable). They contain no fallback measurements or exception traceback. The CLI supplies a request ID per failed run; the API supplies one per request.

## Source access contracts

Checked on 2026-10-30. The following clients are implemented independently behind the shared asynchronous transport and typed provenance envelopes. No client calls another client. Schema parsing lives in a shared helper. A source health entry is based on actual upstream HTTP attempts, not automatic probes. Missing configuration is distinct from an outage.

| Source | Endpoint and request parameters | Limits, licence and attribution | Freshness and missing values |
| --- | --- | --- | --- |
| Open-Meteo geocoding | https://geocoding-api.open-meteo.com/v1/search with name, count=5, language, format=json, countryCode=IN | [Official docs](https://open-meteo.com/en/docs/geocoding-api); common Open-Meteo free non-commercial call limits apply. CC BY 4.0 with Open-Meteo and GeoNames credit. | One day fresh plus one day stale; no results returns an empty places array and an explicit reason. No default plot. |
| Open-Meteo flood | https://flood-api.open-meteo.com/v1/flood with coordinates, daily=river_discharge, forecast_days=14, timezone=UTC, timeformat=unixtime | [Official docs](https://open-meteo.com/en/docs/flood-api); common Open-Meteo limits and API-data CC BY 4.0. Credit Open-Meteo and GloFAS/Copernicus. | Fifteen minutes fresh plus one hour stale. Null discharge stays null. River grid values do not determine plot inundation. |
| NASA POWER | https://power.larc.nasa.gov/api/temporal/daily/point with community=AG, parameters=T2M,PRECTOTCORR,ALLSKY_SFC_SW_DWN, coordinates, start/end in YYYYMMDD, format=JSON, time-standard=UTC | [Daily API](https://power.larc.nasa.gov/docs/services/api/temporal/daily/) permits at most twenty point parameters. No numeric request-rate ceiling was verified; do not apply unrelated api.nasa.gov limits. [Referencing guide](https://power.larc.nasa.gov/docs/referencing/) requires service name/version and access date, plus NASA POWER and data credit. A named data licence was not established from these pages: licence_url remains null. | One day fresh plus one day stale. Retrospective data, not a forecast; [documented latency](https://power.larc.nasa.gov/docs/faqs/data/) differs for solar and meteorology. The response fill_value becomes null. Service version and source datasets accompany the result. |
| SoilGrids | https://rest.isric.org/soilgrids/v2.0/properties/query with lat, lon, repeated property=clay,sand,silt,phh2o,soc, depth=0-5cm, value=mean | Verified parameters from the live [official OpenAPI schema](https://rest.isric.org/soilgrids/v2.0/openapi.json). [Access documentation](https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs_02.html) publishes five requests/minute and CC BY 4.0; credit ISRIC and SoilGrids 2.0. [REST entry](https://rest.isric.org/) warns of outages. This application's per-process SoilGrids transport spaces attempts by at least twelve seconds. | One day fresh plus one day stale. Topsoil model estimates, not a field test. Raw means and mapped units are retained; values divide by the returned positive d_factor and retain target_units. Null means remain null. |
| Agmarknet | https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070; API key from AGMARKNET_API_KEY, format=json, offset=0, limit=10, state/district/commodity filters | Opened the [official resource page](https://www.data.gov.in/resource/current-daily-price-various-commodities-various-markets-mandi), but it returned an incomplete shell labelled as a sandbox. The official help guide was unavailable; [another official OGD guide](https://event.data.gov.in/wp-content/uploads/2019/12/CPGRAMS_accessing_API_HelpGuide_User.pdf) confirms api-key, format, offset and limit conventions but is for a different resource. Current authenticated schema, filters, rate ceiling, price unit and full licence terms remain unverified. The portal footer names Government Open Data License-India; licence_url remains null until its terms can be read. Credit the publisher via data.gov.in. | Fifteen minutes fresh plus one hour stale when usable. Missing key returns a non-retryable typed unconfigured error, with zero upstream calls. A returned page must not be called the latest price or complete district coverage. No recorded successful authenticated result exists. No price unit is assumed. |

## Observed responses

Real direct requests and requests through the running API returned:

- Geocoding: actual Indian place matches for Kolar. Country filtering does not establish that a selected plot lies in one of the supported districts.
- Flood: fourteen discharge values, with the source's m³/s label preserved. An apparent encoding problem was traced to a local file read and corrected; no upstream unit defect is claimed.
- POWER: seven dates of temperature and rainfall for 2026-10-15 through 2026-10-21. Solar radiation was entirely fill values; those fields are exposed as null with partial status. No solar values were inferred from other parameters.
- SoilGrids: the official schema and query both returned HTTP 200, but all five requested property means were null. The evidence therefore reports empty, not a soil value or a field classification. The official access page has warned about pausing the service; successful requests do not establish stability.
- Agmarknet: an unauthenticated direct request timed out. The configured application has no key and returns an explicit HTTP 503 missing_api_key envelope; no authenticated upstream request or price was verified.

Successful raw responses and their retrieval metadata are isolated under tests/recorded. Application code never reads them. Empty responses are valid evidence of missing coverage, not an invitation to fabricate data.

## Cache and source health

One bounded in-memory cache per source preserves the original source fetch time. A stale response is returned immediately while one refresh runs per key; concurrent callers share that refresh. If all refresh slots are occupied, a still-usable stale entry is returned and refresh is deferred to a later request. Hard expiry removes an entry at fresh TTL plus stale retention, and a failed replacement returns an error. Source errors are never cached as measurements. Entries and simultaneous refreshes are bounded. A cancelled waiting request does not cancel the shared upstream fetch. Shutdown cancels refresh tasks before closing the HTTP client. Policy durations are application settings, not upstream validity guarantees.

/health/sources never probes sources. Unknown status and null checked_at mean no HTTP call has occurred. Unconfigured is a configuration observation. Counters include retries; latency measures the last HTTP attempt. Empty or partial data reports degraded with a reason. Health records the most recent request, not a guaranteed current uptime state. State is per process and is lost at restart; multiple workers need shared pacing/cache coordination before treating per-process quotas as global.



## Retrospective and regional checks

On 2026-10-30 the official NASA [Daily API](https://power.larc.nasa.gov/docs/services/api/temporal/daily/) and [latency FAQ](https://power.larc.nasa.gov/docs/faqs/data/) were opened. Daily UTC/LST coverage is documented from 1981-01-01 to near real time; meteorological latency is two to three days and solar latency five to seven days. Live Kolar requests returned seven non-fill daily values for temperature, corrected precipitation and solar radiation for 2020-01-01 through 2020-01-07. For 2026-09-01 through 2026-09-07, seven temperature/rain values were present and no solar values. For 2026-10-20 through 2026-10-23, four temperature/rain values were present and no solar values. Therefore documented latency does not guarantee recent solar coverage in these runs.

The client and route reject requests before 1981-01-01 or later than seven UTC days ago; the seven-day lag is a conservative application policy for the combined meteorology/solar request, not a claim of guaranteed availability. The optional Plan observation panel requests a completed past week ending eight UTC days ago. POWER evidence carries evidence_role=observation_cross_check; no NASA value feeds deterministic future tasks or the forecast chart. Missing observations still remain null. No calculated cross-source error score is implied without an alignment service.

SoilGrids was tested at five coordinates with clay, sand, silt, phh2o and soc, mean values, and depths 0-5cm, 5-15cm and 15-30cm. All requests returned HTTP 200. Every tested mean was null:

| Location | Latitude, longitude | Non-null / requested means |
| --- | --- | --- |
| Bengaluru Rural | 13.29, 77.54 | 0 / 15 |
| Kolar | 13.14, 78.13 | 0 / 15 |
| Tumakuru | 13.34, 77.10 | 0 / 15 |
| Chikkaballapura | 13.43, 77.73 | 0 / 15 |
| Ramanagara | 12.72, 77.28 | 0 / 15 |

The repeated-property/depth query agrees with the official schema. A single-property/single-depth Kolar request also returned null; the same clay/0-5cm/mean request at 51.99, 5.66 (Netherlands control) returned mapped mean 170 with source conversion factor 10. This rules out a universal failure of the request shape, but does not establish whether Karnataka nulls reflect coverage, a spatial backend failure or another source condition. No regional soil suitability is inferred. Soil is optional in both the plan response notes and visible product; it is fetched only when explicitly requested and cannot block or supply defaults to the weather plan.

DATA_GOV_IN_API_KEY was absent in the environment during the requested check. No authenticated market request or price was verified. The app accepts this variable as primary and retains AGMARKNET_API_KEY as a backwards-compatible alias. Keys never enter browser code or public source URLs.

## Backtest inputs

Verified on 2026-10-30 against the official [Previous Runs](https://open-meteo.com/en/docs/previous-runs-api) and [Historical Weather](https://open-meteo.com/en/docs/historical-weather-api) pages and real requests. Fixed GFS Global leads 1–7 are paired with ERA5; neither request uses a key. Existing Open-Meteo free-use budgets and CC BY 4.0 attribution apply. Results carry public request URLs, model/grid coordinates, fetch times and attribution for both inputs. These are gridded estimates; model grid cells differ.

ERA5 is documented as updating daily with five days' delay. A 60-day comparison ends six UTC days ago and requests the next date for the precipitation boundary hour. The real 2026-08-26 through 2026-10-24 comparison had all 1,440 temperature hours but excluded the last rain day because the following midnight ERA5 value was null. No missing value was filled. Full coverage and metric definitions are in BACKTEST.md. A multi-variable 61-date request may consume more than one source billing unit; no exact workload quota cost is claimed.

On 2026-10-31, a further real request at Kolar (13.13768, 78.12999) returned a typed SoilGrids HTTP 503 failure. The visible plan remained available. This is a later availability observation, not evidence that earlier nulls were corrected or that new soil values exist.

Hosted storage/API provider limits, official pricing URLs and the 2026-10-31 check are recorded in RUNBOOK.md. Database hosting is not an agronomic evidence source and no provider account was created. The demonstration failure switch is off by default and emits a typed error before any upstream request; it never supplies a source measurement.


## Packaged district boundaries

Automatic district identification uses [geoBoundaries gbOpen India ADM2](https://www.geoboundaries.org/api/current/gbOpen/IND/ADM2/), boundary ID IND-ADM2-76128533, representing 2021. The published metadata names Pathways Data Pvt. Ltd. and lgdirectory.gov.in as the source and Open Data Commons Open Database License 1.0 as the licence. The [pinned simplified GeoJSON](https://github.com/wmgeolab/geoBoundaries/raw/9469f09/releaseData/gbOpen/IND/ADM2/geoBoundaries-IND-ADM2_simplified.geojson) was downloaded on 2026-10-31. The API metadata declares 736 units; the actual downloaded file has 735 features. Missing coverage is never filled by inference.

The packaged files are apps/api/src/sowcast/geography/data/india-districts.json and provenance.json. Only insignificant JSON whitespace was removed; all source geometry and properties are retained. Provenance includes the original and packaged SHA-256 hashes, the source URLs, retrieval timestamp, licence and actual feature count. Data is redistributed under [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/). The lookup response and UI retain attribution and the licence link.

The backend loads the polygons once, filters by bounding boxes and uses point-in-polygon checks with hole support. Edge and overlapping matches require manual confirmation. Lookup sends no coordinates to an external geocoding provider and makes no network request at runtime. Simplified historical boundaries are approximate; recent renamings or boundary changes are not asserted. Non-pilot district names remain as written in the source. Identifying an administrative area does not establish field conditions or activate additional crop rules. The existing five-district agronomic scope remains.


## ERA5 historical chart reference

The chart uses 1991–2020, the current 30-year reference period described by [WMO](https://community.wmo.int/site/knowledge-hub/programmes-and-initiatives/climate-services/wmo-climatological-normals). These are application-computed daily reanalysis averages, not WMO-certified station normals. The [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api) documents consistent multidecadal ERA5 coverage, daily extrema/precipitation and its approximately 0.25-degree grid. Forecast best-match grids can differ from the historical grid; both requested and historical grid coordinates remain visible. UTC daily boundaries are retained.

A real Kolar request at 13.14, 78.13 returned 10,958 daily rows over 1991-01-01 through 2020-12-31, with zero nulls across the three selected fields, on 2026-10-31. Its ERA5 grid was 13.25, 78.25. The direct request took 1.23 seconds locally. The API summary completed in 1.296 seconds on its first request; the next request reused the summary without another upstream call. For October 31 the computed average daily low/high were 18.97 and 26.403333333333332 degrees Celsius and average precipitation was 4.846666666666667 mm, with 30 samples for each field. These are observed local verification results, not hosted latency guarantees.

Means use arithmetic averaging by calendar day with math.fsum. Requiring every expected sample is a conservative application policy; no missing-year imputation, smoothing or leap-day interpolation is applied. A daily rainfall average includes dry and wet years and is not a probability or a prediction of drizzle. No station calibration, normal-based risk threshold or irrigation calculation is derived from this comparison. Real source data and request/fetch metadata are retained only under tests/recorded for offline regression; runtime fetches the service and never reads those recordings. A 30-year request may consume more than one provider billing unit; the single HTTP-attempt count is not a quota-cost claim.
