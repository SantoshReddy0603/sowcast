# API contract

The contract version is 1.0. Evidence, plan, answer and error responses include api_version; /health and /ready return small status objects; plan requests may omit it to select 1.0, while any other supplied version is rejected. Breaking shape or semantic changes require a new contract version. The complete machine-readable request/response field definitions, types, nullability and defaults are in [api-schema.json](api-schema.json). The server also serves /openapi.json and /docs.

## POST /v1/plans

The body requires latitude and longitude (finite WGS84 coordinates), crop (ragi, paddy, maize, tur, groundnut or tomato) and sowing_status (not_sown or growing). It rejects unknown top-level fields. sowing_date is an optional ISO date: an existing sowing date is invalid for not_sown. growth_stage is optional flowering/other and may be absent; null does not invent a stage. agronomy_context contains the district, explicit FAO-reference choice, optional observed water-stage interval and field-management flags documented in AGRONOMY.md. Its planting_date field is retained for compatibility; when both dates are supplied they must match. sowing_date is canonical and is echoed in the response. No sowing date is inferred when it is absent.

The response contains api_version, crop, location, rule_version, date_basis, sowing_status, growth_stage, sowing_date, agronomy_context, actions, disabled_parameters, regional_sowing_window, water_balance_availability, limitation and the complete weather evidence. Each action retains its date, kind, deterministic reason, optional guarded agent explanation, rule version, typed metrics, exact weather input references, crop citations and reference water-balance details. Unknown metrics use status insufficient_data and value null, not zero. No water-balance rule is claimed for ragi or tur. UTC daily boundaries are explicit. The optional forecast_reliability list holds GFS-versus-ERA5 rain agreement sentences for leads 1-7 when a non-stale backtest for that location is already cached; it is never computed during a plan request, is empty otherwise, and comes from a different model than the plan forecast.

## GET /v1/evidence/weather

Required query parameters are latitude and longitude. The response includes api_version, source, attribution_url, attribution_text, licence_url, modifications, request_url, fetched_at, is_stale, data_status, missing_reasons, location, grid_location, timezone, hourly and daily. Series contain time, values and units. Numeric measurements may be null; arrays align with time. The original fetch timestamp is retained on cached/stale responses. A UTC valid time is not a fetch timestamp or forecast issue time.

## Errors and request IDs

The error body is api_version plus error containing code, message, source (nullable for local validation), retryable and request_id. Every handled HTTP response has a server-generated X-Request-ID header matching the error ID when present. Source failures use 503; missing keys use a readable non-retryable source error with no upstream call; validation uses 422; unknown routes use the same error shape. Unexpected internal errors return a fixed retryable 500 internal_error envelope without exception details. Source URLs and messages must not include credentials.

## Other routes

GET /health reports process availability. GET /health/sources performs no probes: unknown/checked_at null means no upstream call; unconfigured describes missing credentials, not an outage. Counters count actual HTTP attempts, including retries. Latency is the last attempt latency. Available/degraded/unavailable describe the most recently requested data, not guaranteed current source availability. Cached responses do not create health requests.

GET /v1/places accepts name and an optional supported language. GET /v1/evidence/flood and /soil accept coordinates. GET /v1/evidence/power also requires start_date and end_date, ordered and at most 61 inclusive days. GET /v1/evidence/mandi accepts district and commodity, requires DATA_GOV_IN_API_KEY or its legacy alias AGMARKNET_API_KEY and returns a bounded page rather than a latest-price claim. Source evidence has the same provenance/freshness fields, plus typed source-specific data. Empty and partial responses expose missing_reasons. Soil/flood observations do not determine plot waterlogging or flood risk.

## Real request examples

The following requests ran against local servers on 1 November 2026 at latitude 13.14, longitude 78.13. Forecast, flood and climate requests reached their public upstream sources. Backtest returned an existing real result computed earlier that day; its 0.010-second response is a database/cache retrieval, not a cold recompute. Gemini and authenticated market access remain UNVERIFIED because no keys are configured. The sowing date is a calculation scenario, not a verified farm observation.

POST /v1/plans body:

```json
{
  "api_version": "1.0",
  "latitude": 13.14,
  "longitude": 78.13,
  "crop": "maize",
  "sowing_status": "growing",
  "sowing_date": "2026-10-01",
  "agronomy_context": {
    "district": "Kolar",
    "allow_fao_reference": true
  },
  "language": "en"
}
```

HTTP 200, X-Request-ID: e36cece9-17b4-479d-93b4-627320ffe3c9. The response contained 14 actions. This excerpt preserves the first action and its exact input references; remaining actions and fields are omitted here only.

```json
{
  "api_version": "1.0",
  "crop": "maize",
  "location": {
    "latitude": 13.14,
    "longitude": 78.13
  },
  "rule_version": "1.1.1",
  "sowing_date": "2026-10-01",
  "actions": [
    {
      "date": "2026-11-01",
      "kind": "review_water_balance",
      "reason": "2026-11-01 UTC forecast: rainfall 0.30 mm against reference maize development ETc 2.48 mm (Kc 0.609 × ET0 4.07 mm); gross-rainfall shortfall 2.18 mm. Review soil moisture and irrigation records; this is not an irrigation dose. FAO reference values are not locally calibrated.",
      "inputs": [
        {
          "source": "open_meteo_forecast",
          "request_url": "https://api.open-meteo.com/v1/forecast?latitude=13.14&longitude=78.13&hourly=temperature_2m%2Cprecipitation%2Cet0_fao_evapotranspiration%2Csoil_moisture_0_to_1cm%2Cwind_speed_10m&daily=temperature_2m_max%2Ctemperature_2m_min%2Cprecipitation_sum%2Cet0_fao_evapotranspiration&forecast_days=14&timezone=UTC&timeformat=unixtime&temperature_unit=celsius&wind_speed_unit=kmh&precipitation_unit=mm",
          "fetched_at": "2026-11-01T08:04:21.337729Z",
          "is_stale": false,
          "field": "daily.values.temperature_2m_min[0]",
          "valid_at": "2026-11-01T00:00:00Z",
          "value": 19.6,
          "unit": "°C"
        },
        {
          "source": "open_meteo_forecast",
          "request_url": "https://api.open-meteo.com/v1/forecast?latitude=13.14&longitude=78.13&hourly=temperature_2m%2Cprecipitation%2Cet0_fao_evapotranspiration%2Csoil_moisture_0_to_1cm%2Cwind_speed_10m&daily=temperature_2m_max%2Ctemperature_2m_min%2Cprecipitation_sum%2Cet0_fao_evapotranspiration&forecast_days=14&timezone=UTC&timeformat=unixtime&temperature_unit=celsius&wind_speed_unit=kmh&precipitation_unit=mm",
          "fetched_at": "2026-11-01T08:04:21.337729Z",
          "is_stale": false,
          "field": "daily.values.temperature_2m_max[0]",
          "valid_at": "2026-11-01T00:00:00Z",
          "value": 27.6,
          "unit": "°C"
        },
        {
          "source": "open_meteo_forecast",
          "request_url": "https://api.open-meteo.com/v1/forecast?latitude=13.14&longitude=78.13&hourly=temperature_2m%2Cprecipitation%2Cet0_fao_evapotranspiration%2Csoil_moisture_0_to_1cm%2Cwind_speed_10m&daily=temperature_2m_max%2Ctemperature_2m_min%2Cprecipitation_sum%2Cet0_fao_evapotranspiration&forecast_days=14&timezone=UTC&timeformat=unixtime&temperature_unit=celsius&wind_speed_unit=kmh&precipitation_unit=mm",
          "fetched_at": "2026-11-01T08:04:21.337729Z",
          "is_stale": false,
          "field": "daily.values.precipitation_sum[0]",
          "valid_at": "2026-11-01T00:00:00Z",
          "value": 0.3,
          "unit": "mm"
        },
        {
          "source": "open_meteo_forecast",
          "request_url": "https://api.open-meteo.com/v1/forecast?latitude=13.14&longitude=78.13&hourly=temperature_2m%2Cprecipitation%2Cet0_fao_evapotranspiration%2Csoil_moisture_0_to_1cm%2Cwind_speed_10m&daily=temperature_2m_max%2Ctemperature_2m_min%2Cprecipitation_sum%2Cet0_fao_evapotranspiration&forecast_days=14&timezone=UTC&timeformat=unixtime&temperature_unit=celsius&wind_speed_unit=kmh&precipitation_unit=mm",
          "fetched_at": "2026-11-01T08:04:21.337729Z",
          "is_stale": false,
          "field": "daily.values.et0_fao_evapotranspiration[0]",
          "valid_at": "2026-11-01T00:00:00Z",
          "value": 4.07,
          "unit": "mm"
        }
      ]
    }
  ],
  "evidence": {
    "source": "open_meteo_forecast",
    "fetched_at": "2026-11-01T08:04:21.337729Z",
    "data_status": "complete",
    "is_stale": false,
    "attribution_text": "Weather data by Open-Meteo.com"
  }
}
```

| Request | Actual result |
| --- | --- |
| GET /v1/evidence/weather?latitude=13.14&longitude=78.13 | 200; 14 forecast days; fetched 2026-11-01T08:04:21.337729Z. |
| GET /v1/evidence/flood?latitude=13.14&longitude=78.13 | 200; river discharge evidence fetched 2026-11-01T08:04:22.268563Z. |
| GET /v1/backtests?latitude=13.14&longitude=78.13 | 200; seven leads; result computed 2026-11-01T07:52:08.906152Z. |
| GET /v1/climate-normals?latitude=13.14&longitude=78.13 | 200; 366 calendar-day entries; complete coverage. |
| POST /v1/chat with the same plot and a typed question | 200;status=unavailable; provider_unconfigured in its trace; no accepted model claims. |

The plan issued a trace capability kept only in memory during this check. GET without it returned 404; authorized GET returned 200 with 56 input references, rule_version=1.1.1, latency_ms=262.541 and provider_requests=0. Authorized DELETE returned 204; reading after deletion returned 404. Raw capability values are not included here.

A separate local API with SOWCAST_UNAVAILABLE_SOURCE=open_meteo_forecast returned HTTP 503 for the same plan request:

```json
{
  "api_version": "1.0",
  "error": {
    "code": "source_unavailable",
    "message": "Open-Meteo forecast: Source is disabled for this demonstration (retryable)",
    "source": "Open-Meteo forecast",
    "retryable": true,
    "request_id": "8850bc37-6287-4e88-a38b-3f2f5d2a204a"
  }
}
```

## District identification

GET /v1/places/district requires finite latitude and longitude. It performs local point-in-polygon lookup against the packaged geoBoundaries gbOpen India ADM2 simplified geometry. The response includes location, status (matched, ambiguous or unavailable), district, supported_district, source URL, attribution, licence, boundary_year=2021 and a limitation. District is populated only for a single unambiguous polygon match; shared edges, overlaps and unrecognised coordinates are not guessed. supported_district is non-null only for the five pilot districts. Historical Bangalore Rural and Tumkur labels map to the existing Bengaluru Rural and Tumakuru request names. Other source names are retained and do not enable pilot guidance.

This route makes no upstream call and is independent of Gemini. Invalid/missing coordinates use the existing 422 envelope. The Plot UI rechecks after map clicks, map-centre selection, place search and coordinate edits. It cancels outdated responses, clears the old selection, shows lookup progress and permits manual correction. An outside-pilot match displays its actual source district name and submits district=null with allow_fao_reference=false; a boundary/unknown/failed lookup asks for manual confirmation. See DATA_SOURCES.md for data vintage and provenance. This lookup does not extend agronomic coverage. Plan and chat independently enforce a pilot-district match on the server.

## Optional evidence contract

Plan now also includes optional_evidence_notes. Soil availability never gates deterministic weather tasks. NASA POWER evidence includes evidence_role=observation_cross_check. Its route and client accept only UTC dates from 1981-01-01 through seven days before the current UTC date; the conservative lag avoids requesting forecast/recent dates from a retrospective product. Null values remain possible inside this range. The visible app requests the completed week ending eight days ago and does not use these observations as forecast inputs. DATA_GOV_IN_API_KEY is the primary market environment variable, with AGMARKNET_API_KEY retained as an alias.

## Explanations, questions and traces

POST /v1/plans accepts language=en|hi|kn|te|ta|mr (default en). It adds agent_note and trace_id. Each dated action adds explanation_status, explanation_sources and the existing explanation text; unavailable generation leaves the deterministic reason intact. POST /v1/chat accepts question (1–2000 characters), plot (the same validated plan request) and language. It returns status=verified|unavailable, claims, facts, code-formatted facts, a trace_id, a visible note and the available structured plan. GET /v1/traces/{UUID} requires Authorization: Bearer with the response-issued trace_access_token and returns the compact execution summary; missing/wrong capabilities and absent IDs return the same404 project error envelope. DELETE requires the same capability and returns204. See api-schema.json and AGENT.md for the complete contract and numeric limitations.

Live Gemini plan and chat generation is UNVERIFIED without configured credentials, an explicit model and usable quota. Offline guardrail/provider checks do not establish successful live generation; deterministic reasons, values and calculations remain code-owned.

## Backtests

GET /v1/backtests?latitude=12.97&longitude=77.59 returns seven GFS model leads. Each lead includes temperature MAE with paired/missing hours and rain_definitions for gt0 (>0 mm) and ge1 (≥1 mm). Each definition carries paired/missing days, correct days, accuracy, ERA5 rain count/share, majority class/count/accuracy and an approximate 95% Wilson interval. Flat rain fields remain gt0 aliases. Null rates/intervals mean no usable pairs, not zero accuracy. No ranking is established. The majority baseline is fitted retrospectively to that paired sample.

Source failures and active jobs use the project error envelope; active ownership elsewhere is retryable 503/backtest_in_progress. Invalid coordinates return 422. Completed summaries are reused for up to one day. Refresh checks the window/cache rather than forcing source traffic. Backtest facts returned by chat identify the GFS model lead, rain definition and sample size using code-owned labels.

This real request returned HTTP 200, X-Request-ID c240e23c-6b95-4e84-b687-5cea3f891a79. Selected fields below show the first of seven lead results; the full API also returns both sources and limitations:

```json
{
  "methodology_version": "1.1.0",
  "location": {
    "latitude": 12.97,
    "longitude": 77.59
  },
  "start_date": "2026-08-27",
  "end_date": "2026-10-25",
  "computed_at": "2026-10-31T03:04:01.203048Z",
  "data_status": "partial",
  "uncertainty_note": "About 59 paired days is a small sample. Differences of a few days between leads are small relative to sampling uncertainty; no lead ranking is established. The 95% Wilson intervals assume independent days; weather correlation can widen uncertainty. These marginal intervals are not a paired test between leads.",
  "scores": [
    {
      "lead_days": 1,
      "lead_hours": 24,
      "temperature_mae_c": 1.339375,
      "temperature_pairs": 1440,
      "temperature_missing_hours": 0,
      "rain_correct_days": 41,
      "rain_pairs": 59,
      "rain_missing_days": 1,
      "rain_accuracy": 0.6949152542372882,
      "era5_rain_days": 36,
      "era5_rain_share": 0.6101694915254238,
      "majority_correct_days": 36,
      "majority_accuracy": 0.6101694915254238,
      "rain_definitions": [
        {
          "definition": "gt0",
          "event": "Daily precipitation strictly greater than 0 mm.",
          "paired_days": 59,
          "missing_days": 1,
          "correct_days": 41,
          "accuracy": 0.6949152542372882,
          "accuracy_ci95": [
            0.5685367346805482,
            0.7974636801988394
          ],
          "era5_rain_days": 36,
          "era5_rain_share": 0.6101694915254238,
          "majority_class": "rain",
          "majority_correct_days": 36,
          "majority_accuracy": 0.6101694915254238
        },
        {
          "definition": "ge1",
          "event": "Daily precipitation at least 1 mm.",
          "paired_days": 59,
          "missing_days": 1,
          "correct_days": 44,
          "accuracy": 0.7457627118644068,
          "accuracy_ci95": [
            0.6220385597107273,
            0.839440224267631
          ],
          "era5_rain_days": 18,
          "era5_rain_share": 0.3050847457627119,
          "majority_class": "no_rain",
          "majority_correct_days": 41,
          "majority_accuracy": 0.6949152542372882
        }
      ],
      "rain_brier": null,
      "brier_reason": "No true precipitation probabilities are provided by these requests."
    }
  ]
}
```

See BACKTEST.md for UTC hour-ending aggregation, source delay, baselines, interval assumptions, actual gaps and the precompute command.

## Operational HTTP behavior

GET /health returns {"status":"ok"} without a source or database request. GET /ready returns {"status":"ready"} after querying storage. Host health and opt-in keep-alive use /health; manual readiness is a normal limited request. Startup migrates before accepting traffic. Database failures use 503/storage_unavailable with a safe message and request ID.

Limits apply over a sliding 60-second process-local window. General requests and combined plan/chat/backtest budgets are documented in RUNBOOK.md. Limit errors use 429, Retry-After and X-Request-ID; CORS exposes these headers for exact configured origins. A real one-request-budget server returned 200 and then:

```json
{"api_version":"1.0","error":{"code":"rate_limited","message":"Request limit reached; retry after the indicated delay.","source":"Sowcast API","retryable":true,"request_id":"17145910-7f19-40ed-b169-58b4017042ff"}}
```

CORS_ORIGINS permits explicit HTTP origins; no wildcard or credential grant is used. Proxy headers are not accepted from arbitrary clients. The server-configured demonstration switch returns a normal typed source failure, not test data. The real switched forecast request returned HTTP 503 with no values:

```json
{"api_version":"1.0","error":{"code":"source_unavailable","message":"Open-Meteo forecast: Source is disabled for this demonstration (retryable)","source":"Open-Meteo forecast","retryable":true,"request_id":"d9361fbd-5d8a-4ad9-8393-dc05df575406"}}
```


## Historical climate comparison

GET /v1/climate-normals requires finite latitude and longitude. It returns the complete 366-entry calendar-day summary for the requested location, the actual ERA5 grid location, model, period start_date=1991-01-01 and end_date=2020-12-31, units, source/fetch/licence metadata, coverage status and limitations. Each day has month_day, nullable values for temperature_2m_min, temperature_2m_max and precipitation_sum, a samples count for each field, and expected_samples. Ordinary days expect 30 samples; February 29 expects eight. A mean is available only when every expected year for that calendar day and variable is present. Missing means are null, never zero or interpolated.

The source is a real Open-Meteo archive request for ERA5 daily extrema and precipitation, with UTC boundaries and explicit units. Invalid dates, duplicate/non-midnight timestamps, non-UTC offsets, malformed/nonfinite measurements, reversed extrema and negative rain produce typed source failures. Completed summaries use a process-local cache for seven days, with stale-while-revalidate for a further 30 days, four entries/pending requests and coalescing for identical coordinates. Cached fetch times are preserved; restart empties this cache. The route has its own expensive-request budgets; it shares the archive source transport and health counter with backtests. An upstream archive failure returns the normal source error envelope and never blocks a weather plan.

The chart requests the comparison separately after a plan appears. It matches by UTC calendar month/day, so year-crossing forecasts and leap days do not shift the reference. Forecast bands/bars remain distinct from dashed historical-average lines. Source failure, loading, empty, partial and stale states remain visible. This endpoint does not supply facts to the agent or modify agronomic actions.

## Private execution traces

Plan responses include nullable trace_id/trace_access_token; chat responses include both strings. Keep the token private and out of URLs, logs and persistent browser storage. GET /v1/traces/{UUID} and DELETE /v1/traces/{UUID} require Authorization: Bearer <trace_access_token>. UUID alone is insufficient. Missing/wrong tokens and missing/deleted records return indistinguishable 404 envelopes; malformed identifiers return 422. Authorized deletion returns an empty 204 response. Responses never expose stored token digests. CORS permits Authorization and DELETE only for explicitly configured origins. Refresh an older client response to obtain a new protected trace; legacy rows have no HTTP access. This capability protects an execution summary, not a user account or a farm record.

## Regional request validation

POST /v1/plans and POST /v1/chat resolve the submitted coordinates against the packaged district boundaries before source or model work. Ocean, outside-pilot and uncertain boundary points return 422 in the existing error envelope. Local advice is limited to Bengaluru Rural, Kolar, Tumakuru, Chikkaballapura and Ramanagara. The server replaces any caller-supplied district with its resolved district; a client cannot select another district to enable its rules. Boundary-data failures return a typed retryable 503 without advice. Global weather evidence remains available separately.

Sowing and reference planting dates must be from 2020-01-01 through one calendar year after the current UTC date. Invalid dates return a field-specific validation message. Chat messages must contain non-whitespace text; surrounding whitespace is stripped. These checks run before source requests.

Climate requests have a separate 15/IP and 20/process per-minute budget. Backtests retain 5/IP and 10/process; combined plans/chat retain 10/IP and 10/process. All also consume the general 120/IP budget. Every limit is process-local and denied work returns 429 with Retry-After.
