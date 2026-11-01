# Backtest methodology

GFS Global forecasts at fixed leads of 24, 48, 72, 96, 120, 144 and 168 hours are compared against ERA5 reanalysis for the same requested coordinates and valid time. ERA5 is a gridded reference, not a plot observation. This comparison does not validate the live best-match forecast blend, agronomy rules, alerts or crop outcomes.

## Sources and window

The official [Previous Runs documentation](https://open-meteo.com/en/docs/previous-runs-api), checked on 2026-10-30, defines `_previous_day1` through `_previous_day7` as fixed offsets of 24–168 hours before valid time. It distinguishes this from retrieving an exact initialization through Single Runs. Most model archives start in January 2024; coverage varies. Free-use terms and attribution are in DATA_SOURCES.md. No API key is required for the free endpoints.

Forecast endpoint: `https://previous-runs-api.open-meteo.com/v1/forecast`, with `models=gfs_global` and hourly `temperature_2m_previous_dayN,precipitation_previous_dayN` for N=1..7. Reference endpoint: `https://archive-api.open-meteo.com/v1/archive`, with `models=era5` and hourly `temperature_2m,precipitation`. Both use requested latitude/longitude, `timezone=UTC`, `timeformat=unixtime`, `temperature_unit=celsius` and `precipitation_unit=mm`. Returned grid coordinates, request URLs, attribution and fetch times remain in the result.

The [Historical Weather documentation](https://open-meteo.com/en/docs/historical-weather-api) lists ERA5 at 0.25° resolution with daily updates and five days' delay. The inclusive 60-day comparison window ends six UTC calendar days before the request date. Publication gaps can still occur and remain explicit. The start date is the end date minus 59 days.

Precipitation is a preceding-hour sum according to the hourly parameter definitions. A UTC rain day therefore uses values ending at 01:00 through 00:00 the following day. Clients request one extra calendar date for that boundary value: 61 source dates, up to 1,464 timestamps, while only 60 days are scored. Temperature uses the 1,440 instantaneous hours from the first 00:00 through the last 23:00. Extra hours never enlarge the denominator. No local-time conversion or interpolation is applied.

## Alignment and metrics

Inputs must have the same requested plot, expected models and units, increasing unique timestamps and no stale flag. Clients reject non-hourly timestamps, non-UTC offsets, negative precipitation, nonfinite values and unexpected units. Source grids can differ; their actual coordinates are shown.

For each lead independently:

- Temperature MAE in °C is `sum(abs(forecast-reference))/paired_hour_count`. Only valid-time pairs with both values count. Expected coverage is 1,440 hours. No pairs returns null, not zero.
- Daily precipitation sums all 24 preceding-hour amounts in that UTC day for each source. Missing either source's hour excludes the whole rain day. Two diagnostic events are reported: daily precipitation strictly greater than 0 mm (gt0), and daily precipitation at least 1 mm (ge1, inclusive). Daily sums use math.fsum to avoid classifying ten 0.1 mm amounts below 1 mm because of floating-point accumulation. This is a declared verification definition, not a crop or sowing threshold.
- Rain accuracy is `matching_rain_or_no_rain_days/paired_day_count`, with numerator, denominator and missing-day count exposed. Expected coverage is 60 days. No usable days returns null. This is raw agreement, not skill relative to a climatological or majority-class baseline; it can look high when one class dominates.
- A pure Brier helper implements `mean((probability-observed_event)^2)` for aligned true probabilities in [0,1]. These deterministic requests provide no compatible probability series, so the API returns `rain_brier=null` with a reason. Rain flags are never substituted for probabilities.

Methodology version is `1.1.0`; older cached summaries use a different key and are not reused. Missing samples are neither filled nor extrapolated. Scores have no station validation, regional calibration or guarantee of future performance. Rain agreement has approximate 95% Wilson intervals with the assumptions below; these are not evidence of a ranking between leads.

## Base rates and uncertainty

Each lead has a rain_definitions entry for gt0 and ge1. Each entry includes paired_days, missing_days, correct_days, accuracy, era5_rain_days, era5_rain_share, majority_class, majority_correct_days, majority_accuracy and accuracy_ci95. The base rate and majority baseline use exactly the same paired-day mask as that lead’s accuracy; missing forecast days do not remain in their denominators. The majority class is rain, no_rain or tie; all rates and intervals are null when no paired days exist. Counts remain explicit. The original flat rain fields, plus their flat base-rate and majority fields, refer to gt0 for compatibility.

The majority baseline always predicts the more common ERA5 outcome in the same sample. It is a retrospective, fitted-to-the-window comparison, not an operational forecast or an independent holdout test. Always-majority accuracy is max(wet_days,dry_days)/paired_days. ERA5 rain-day share is wet_days/paired_days.

For approximate 95% Wilson intervals, use p=correct/paired_days and z=1.959963984540054. The center is (p+z²/(2n))/(1+z²/n), with half-width z*sqrt(p*(1-p)/n+z²/(4n²))/(1+z²/n). The [NIST confidence-interval reference](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm) was opened and read on 2026-10-31. The formula assumes independent binomial outcomes. Weather days are correlated, so these intervals may understate uncertainty. They are marginal intervals, not a paired significance test between leads. No lead is ranked or described as better. With about 59 paired days, differences of a few correct days are small relative to sampling uncertainty. Sparse/empty results use wording based on their actual sample counts.

The UI labels the figures GFS model. The plan continues using Open-Meteo best-match forecasts; changing that source merely to match the backtest would change plan behavior. UTC days correspond to 05:30 IST through 05:30 IST the next day (IST=UTC+05:30), not Indian midnight-to-midnight days.

## Shared execution and deduplication

`GET /v1/backtests?latitude=12.97&longitude=77.59`, the agent's `get_backtest` tool and these commands use the same service:

```sh
python -m sowcast backtest --latitude 12.97 --longitude 77.59
python -m sowcast backtest --latitude 12.97 --longitude 77.59 --scheduled
```

Invalid coordinates use the API error envelope or a readable CLI validation error. Source failures are typed and never supply fabricated scores. `--scheduled` is a one-shot command for an external scheduler, not an in-process timer. Use the installed Python interpreter and command in cron, Windows Task Scheduler or another scheduler. No recurring system task has been installed.

SQLAlchemy stores completed summaries and job leases in DATABASE_URL when configured, otherwise local SQLite at SOWCAST_BACKTEST_DB (default .sowcast/backtest.sqlite3). Alembic upgrades are applied before use; hosted deployment requires PostgreSQL with certificate-validated TLS. Workers must share the same database to deduplicate across processes. Keys include exact coordinates, cutoff date and methodology version, which fixes model, leads and UTC semantics. Atomic transactions elect one owner; five-minute leases permit crash recovery. Owner checks stop old workers releasing or replacing newer jobs. Ownership elsewhere returns a typed retryable `backtest_in_progress` response; retry later. Within a process, concurrent callers await a shared shielded task, so one disconnected caller does not cancel shared work.

The service has a 90-second work deadline, at most 32 pending jobs per process and 32 active leases in the shared database, 128 retained summaries and a one-day result lifetime. Cancelled or failed workers release leases. Expired results are recomputed; stale scores are not silently returned. The view supports stale flags defensively, but the service returns fresh cached or newly computed results. Separate hosts with separate SQLite files do not deduplicate. PostgreSQL workers coordinate transaction locks in their shared database. Database migrations are implemented; distributed scheduling is not installed.

## Cold recompute and precompute

On 2026-10-31, a new CLI process with a fresh empty backtest database completed real network retrieval and computation in 2.252 seconds. A second process reused its persisted result in 0.950 seconds. A separate fresh API database produced a cold HTTP 200 in 1.166 seconds and a cached HTTP 200 in 0.026 seconds. Health counters increased from zero to one request for each source, then stayed at one after the cached request. These are single local measurements, including real source latency, not a distribution or hosted cold-start measurement.

The observed cold HTTP request fits a conservative 30-second benchmark budget. As a specific free-tier reference, the official [Vercel duration page](https://vercel.com/docs/functions/configuring-functions/duration), read on 2026-10-31, lists Hobby Fluid Compute default and maximum at 300 seconds. This is not a claim that the API is deployed on Vercel or that every free-tier proxy has that limit. Source retries can take longer than this observed run; the service allows 90 seconds. Hosted startup, deployment-specific timeouts and free-tier capacity remain unverified until deployment preparation. A local success cannot prove production timeout compatibility.

Before a demo, run the following from the same working directory and with the same SOWCAST_BACKTEST_DB as the API:

```sh
python -m sowcast backtest --latitude 12.97 --longitude 77.59 --scheduled
```

Then open Reliability or call GET /v1/backtests for that plot to confirm a cache hit and current sample counts. Precompute shortly before the demo; the key changes at UTC midnight. The command is repeatable and does not install a recurring task.

## Real verification

The revised real HTTP request returned 200 for 12.97, 77.59, computed at `2026-10-31T03:04:01.203048Z`, over 2026-08-27 through 2026-10-25. Overall status is partial. The following are measured results, without a lead ranking.

| GFS model lead | Temperature MAE °C / hourly pairs | >0 mm correct / paired days | ≥1 mm correct / paired days | Missing rain days |
| --- | ---: | ---: | ---: | ---: |
| 24h | 1.3394 / 1440 | 41 / 59 | 44 / 59 | 1 |
| 48h | 1.3029 / 1440 | 44 / 59 | 44 / 59 | 1 |
| 72h | 1.2916 / 1440 | 38 / 59 | 44 / 59 | 1 |
| 96h | 1.4483 / 1440 | 39 / 59 | 46 / 59 | 1 |
| 120h | 1.4362 / 1440 | 36 / 59 | 39 / 59 | 1 |
| 144h | 1.4771 / 1440 | 33 / 59 | 37 / 59 | 1 |
| 168h | 1.4880 / 1440 | 31 / 59 | 36 / 59 | 1 |

For all seven leads in this run, ERA5 rain-day share was **36/59 (61.0%)** under >0 mm and **18/59 (30.5%)** under ≥1 mm. The corresponding retrospective majority baselines were **36/59 (61.0%, always rain)** and **41/59 (69.5%, always no rain)**. These rates are not plot climatological normals.

ERA5 lacked the following-midnight value needed for the final rain day, so that whole day was excluded. All 1,440 scored temperature hours were present. Source grids differ and both URLs/coordinates remain in the response. Brier scores remain null: no true probability pairs exist. Older recorded source fixtures cover the preceding window and remain offline regression inputs, not substituted application data.

These scores come from one location and one 60-day window; they do not describe other plots, seasons or the plan's best-match forecast.

Plans for a location with a cached, non-stale backtest list the GFS-versus-ERA5 rain agreement for leads 1-7 as `forecast_reliability`; it is read from the cache and never computed during a plan request, and it comes from a different model than the plan forecast.

Offline tests cover recordings, valid-time alignment, midnight assignment, missing-hour exclusion, both rain boundaries, paired-mask baselines, empty metrics, Wilson reference values/properties, Brier bounds, source validation, typed failures, job coalescing/ownership/expiry and CLI validation. Browser checks exercise both definitions and actual counts, mobile containment, errors/retry and isolated real-response mutations for empty/stale states.

On 1 November 2026, `python -m sowcast backtest --latitude 13.14 --longitude 78.13` with an empty separate local database completed in 6.165 seconds and produced all seven leads. This measures one local cold recompute including command startup. Source/network variance and hosted cold starts remain outside that measurement.
