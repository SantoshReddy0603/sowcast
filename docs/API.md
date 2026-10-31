# API contract

The contract version is 1.0. Evidence, plan, answer and error responses include api_version; /health and /ready return small status objects; plan requests may omit it to select 1.0, while any other supplied version is rejected. Breaking shape or semantic changes require a new contract version. The complete machine-readable request/response field definitions, types, nullability and defaults are in [api-schema.json](api-schema.json). The server also serves /openapi.json and /docs.

## POST /v1/plans

The body requires latitude and longitude (finite WGS84 coordinates), crop (ragi, paddy, maize, tur, groundnut or tomato) and sowing_status (not_sown or growing). It rejects unknown top-level fields. sowing_date is an optional ISO date: an existing sowing date is invalid for not_sown. growth_stage is optional flowering/other and may be absent; null does not invent a stage. agronomy_context contains the district, explicit FAO-reference choice, optional observed water-stage interval and field-management flags documented in AGRONOMY.md. Its planting_date field is retained for compatibility; when both dates are supplied they must match. sowing_date is canonical and is echoed in the response. No sowing date is inferred when it is absent.

The response contains api_version, crop, location, rule_version, date_basis, sowing_status, growth_stage, sowing_date, agronomy_context, actions, disabled_parameters, regional_sowing_window, water_balance_availability, limitation and the complete weather evidence. Each action retains its date, kind, deterministic reason, optional guarded agent explanation, rule version, typed metrics, exact weather input references, crop citations and reference water-balance details. Unknown metrics use status insufficient_data and value null, not zero. No water-balance rule is claimed for ragi or tur. UTC daily boundaries are explicit.

## GET /v1/evidence/weather

Required query parameters are latitude and longitude. The response includes api_version, source, attribution_url, attribution_text, licence_url, modifications, request_url, fetched_at, is_stale, data_status, missing_reasons, location, grid_location, timezone, hourly and daily. Series contain time, values and units. Numeric measurements may be null; arrays align with time. The original fetch timestamp is retained on cached/stale responses. A UTC valid time is not a fetch timestamp or forecast issue time.

## Errors and request IDs

The error body is api_version plus error containing code, message, source (nullable for local validation), retryable and request_id. Every handled HTTP response has a server-generated X-Request-ID header matching the error ID when present. Source failures use 503; missing keys use a readable non-retryable source error with no upstream call; validation uses 422; unknown routes use the same error shape. Unexpected internal errors are not part of the source-failure contract. Source URLs and messages must not include credentials.

## Other routes

GET /health reports process availability. GET /health/sources performs no probes: unknown/checked_at null means no upstream call; unconfigured describes missing credentials, not an outage. Counters count actual HTTP attempts, including retries. Latency is the last attempt latency. Available/degraded/unavailable describe the most recently requested data, not guaranteed current source availability. Cached responses do not create health requests.

GET /v1/places accepts name and an optional supported language. GET /v1/evidence/flood and /soil accept coordinates. GET /v1/evidence/power also requires start_date and end_date, ordered and at most 61 inclusive days. GET /v1/evidence/mandi accepts district and commodity, requires AGMARKNET_API_KEY and returns a bounded page rather than a latest-price claim. Source evidence has the same provenance/freshness fields, plus typed source-specific data. Empty and partial responses expose missing_reasons. Soil/flood observations do not determine plot waterlogging or flood risk.

## Real request examples

These requests were executed against the local uvicorn server with real upstream services. The maize sowing date is a caller-supplied calculation scenario, not a verified farm observation. API keys are absent from all examples. Excerpts select actual response fields without renaming them; omitted actions/series remain present in the complete response.

POST /v1/plans

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
  }
}
```

HTTP 200; X-Request-ID: 2fff91f0-4961-4b7f-ab89-8d573bb3dfb9.

```json
{
  "api_version": "1.0",
  "crop": "maize",
  "sowing_date": "2026-10-01",
  "rule_version": "1.1.0",
  "date_basis": "UTC forecast days",
  "water_balance_availability": "Reference water balance needs applicable stage inputs and field conditions.",
  "actions": [
    {
      "date": "2026-10-30",
      "kind": "review_water_balance",
      "reason": "2026-10-30 UTC forecast: rainfall 0.00 mm against reference maize development ETc 2.47 mm (Kc 0.557 × ET0 4.44 mm); gross-rainfall shortfall 2.47 mm. Review soil moisture and irrigation records; this is not an irrigation dose. FAO reference values are not locally calibrated.",
      "explanation": null,
      "explanation_status": "unavailable",
      "rule_version": "1.1.0",
      "metrics": {
        "growing_degree_days": {
          "status": "insufficient_data",
          "value": null,
          "unit": "degC_day",
          "reason": "Daily extrema or verified crop base temperature missing."
        },
        "heat_stress_days": {
          "status": "insufficient_data",
          "value": null,
          "unit": "day",
          "reason": "Temperature coverage or verified heat threshold missing."
        },
        "frost_risk": {
          "status": "insufficient_data",
          "value": null,
          "unit": "flag",
          "reason": "Minimum temperature or verified frost threshold missing."
        },
        "rainfall_deficit_against_et0": {
          "status": "available",
          "value": 4.44,
          "unit": "mm",
          "reason": "Reference atmospheric water deficit; not crop water stress or irrigation volume."
        },
        "rainfall_shortfall_against_crop_et": {
          "status": "available",
          "value": 2.473714285714286,
          "unit": "mm",
          "reason": "Gross rainfall shortfall against reference ETc; not irrigation requirement."
        },
        "waterlogging_risk": {
          "status": "insufficient_data",
          "value": null,
          "unit": "flag",
          "reason": "Field storage, drainage, infiltration or verified limit missing."
        },
        "sowing_window_suitability": {
          "status": "insufficient_data",
          "value": null,
          "unit": "flag",
          "reason": "Verified local sowing window, temperature or soil readiness missing."
        }
      },
      "inputs": [
        {
          "source": "open_meteo_forecast",
          "request_url": "https://api.open-meteo.com/v1/forecast?latitude=13.14&longitude=78.13&hourly=temperature_2m%2Cprecipitation%2Cet0_fao_evapotranspiration%2Csoil_moisture_0_to_1cm%2Cwind_speed_10m&daily=temperature_2m_max%2Ctemperature_2m_min%2Cprecipitation_sum%2Cet0_fao_evapotranspiration&forecast_days=14&timezone=UTC&timeformat=unixtime&temperature_unit=celsius&wind_speed_unit=kmh&precipitation_unit=mm",
          "fetched_at": "2026-10-30T16:53:15.840108Z",
          "is_stale": false,
          "field": "daily.values.temperature_2m_min[0]",
          "valid_at": "2026-10-30T00:00:00Z",
          "value": 18.9,
          "unit": "°C"
        },
        {
          "source": "open_meteo_forecast",
          "request_url": "https://api.open-meteo.com/v1/forecast?latitude=13.14&longitude=78.13&hourly=temperature_2m%2Cprecipitation%2Cet0_fao_evapotranspiration%2Csoil_moisture_0_to_1cm%2Cwind_speed_10m&daily=temperature_2m_max%2Ctemperature_2m_min%2Cprecipitation_sum%2Cet0_fao_evapotranspiration&forecast_days=14&timezone=UTC&timeformat=unixtime&temperature_unit=celsius&wind_speed_unit=kmh&precipitation_unit=mm",
          "fetched_at": "2026-10-30T16:53:15.840108Z",
          "is_stale": false,
          "field": "daily.values.temperature_2m_max[0]",
          "valid_at": "2026-10-30T00:00:00Z",
          "value": 28.8,
          "unit": "°C"
        },
        {
          "source": "open_meteo_forecast",
          "request_url": "https://api.open-meteo.com/v1/forecast?latitude=13.14&longitude=78.13&hourly=temperature_2m%2Cprecipitation%2Cet0_fao_evapotranspiration%2Csoil_moisture_0_to_1cm%2Cwind_speed_10m&daily=temperature_2m_max%2Ctemperature_2m_min%2Cprecipitation_sum%2Cet0_fao_evapotranspiration&forecast_days=14&timezone=UTC&timeformat=unixtime&temperature_unit=celsius&wind_speed_unit=kmh&precipitation_unit=mm",
          "fetched_at": "2026-10-30T16:53:15.840108Z",
          "is_stale": false,
          "field": "daily.values.precipitation_sum[0]",
          "valid_at": "2026-10-30T00:00:00Z",
          "value": 0.0,
          "unit": "mm"
        },
        {
          "source": "open_meteo_forecast",
          "request_url": "https://api.open-meteo.com/v1/forecast?latitude=13.14&longitude=78.13&hourly=temperature_2m%2Cprecipitation%2Cet0_fao_evapotranspiration%2Csoil_moisture_0_to_1cm%2Cwind_speed_10m&daily=temperature_2m_max%2Ctemperature_2m_min%2Cprecipitation_sum%2Cet0_fao_evapotranspiration&forecast_days=14&timezone=UTC&timeformat=unixtime&temperature_unit=celsius&wind_speed_unit=kmh&precipitation_unit=mm",
          "fetched_at": "2026-10-30T16:53:15.840108Z",
          "is_stale": false,
          "field": "daily.values.et0_fao_evapotranspiration[0]",
          "valid_at": "2026-10-30T00:00:00Z",
          "value": 4.44,
          "unit": "mm"
        }
      ],
      "citations": [],
      "water_balance": {
        "coefficient": {
          "status": "available",
          "value": 0.5571428571428572,
          "unit": "dimensionless",
          "reason": "Unadjusted FAO-56 reference coefficient."
        },
        "crop_et_mm": {
          "status": "available",
          "value": 2.473714285714286,
          "unit": "mm",
          "reason": "Reference ETc = Kc × ET0."
        },
        "rainfall_shortfall_mm": {
          "status": "available",
          "value": 2.473714285714286,
          "unit": "mm",
          "reason": "Gross rainfall shortfall against reference ETc; not irrigation requirement."
        },
        "stage": "development",
        "stage_basis": "FAO Table 11 India dry/cool October example; projected, not observed stage",
        "citations": [
          {
            "title": "Crop Evapotranspiration: Guidelines for Computing Crop Water Requirements (FAO Irrigation and Drainage Paper 56)",
            "publisher": "Food and Agriculture Organization of the United Nations",
            "url": "https://www.fao.org/4/x0490e/x0490e0b.htm",
            "locator": "Table 11, Maize (grain), October, India (dry, cool), days_initial",
            "statement": "Example stage duration, not an observed phenology boundary or a Karnataka sowing recommendation.",
            "number_as_written": "20",
            "region": "India (dry, cool), October; not district-calibrated"
          },
          {
            "title": "Crop Evapotranspiration: Guidelines for Computing Crop Water Requirements (FAO Irrigation and Drainage Paper 56)",
            "publisher": "Food and Agriculture Organization of the United Nations",
            "url": "https://www.fao.org/4/x0490e/x0490e0b.htm",
            "locator": "Table 11, Maize (grain), October, India (dry, cool), days_development",
            "statement": "Example stage duration, not an observed phenology boundary or a Karnataka sowing recommendation.",
            "number_as_written": "35",
            "region": "India (dry, cool), October; not district-calibrated"
          },
          {
            "title": "Crop Evapotranspiration: Guidelines for Computing Crop Water Requirements (FAO Irrigation and Drainage Paper 56)",
            "publisher": "Food and Agriculture Organization of the United Nations",
            "url": "https://www.fao.org/4/x0490e/x0490e0b.htm",
            "locator": "Table 11, Maize (grain), October, India (dry, cool), days_mid",
            "statement": "Example stage duration, not an observed phenology boundary or a Karnataka sowing recommendation.",
            "number_as_written": "40",
            "region": "India (dry, cool), October; not district-calibrated"
          },
          {
            "title": "Crop Evapotranspiration: Guidelines for Computing Crop Water Requirements (FAO Irrigation and Drainage Paper 56)",
            "publisher": "Food and Agriculture Organization of the United Nations",
            "url": "https://www.fao.org/4/x0490e/x0490e0b.htm",
            "locator": "Table 11, Maize (grain), October, India (dry, cool), days_late",
            "statement": "Example stage duration, not an observed phenology boundary or a Karnataka sowing recommendation.",
            "number_as_written": "30",
            "region": "India (dry, cool), October; not district-calibrated"
          },
          {
            "title": "Crop Evapotranspiration: Guidelines for Computing Crop Water Requirements (FAO Irrigation and Drainage Paper 56)",
            "publisher": "Food and Agriculture Organization of the United Nations",
            "url": "https://www.fao.org/4/x0490e/x0490e0b.htm",
            "locator": "Table 12, i. Cereals group initial column",
            "statement": "Unadjusted FAO reference coefficient for non-stressed well-managed crops; wetting frequency and climate require local adjustment. Tomato mid assumes no tall-staked crop adjustment. Paddy initial assumes the standing-water/subhumid reference regime.",
            "number_as_written": "0.3",
            "region": "International subhumid reference; not calibrated for the named Karnataka districts"
          },
          {
            "title": "Crop Evapotranspiration: Guidelines for Computing Crop Water Requirements (FAO Irrigation and Drainage Paper 56)",
            "publisher": "Food and Agriculture Organization of the United Nations",
            "url": "https://www.fao.org/4/x0490e/x0490e0b.htm",
            "locator": "Table 12, Maize, Field (grain), mid column",
            "statement": "Unadjusted FAO reference coefficient for non-stressed well-managed crops; wetting frequency and climate require local adjustment. Tomato mid assumes no tall-staked crop adjustment. Paddy initial assumes the standing-water/subhumid reference regime.",
            "number_as_written": "1.20",
            "region": "International subhumid reference; not calibrated for the named Karnataka districts"
          }
        ],
        "warning": "Unadjusted FAO estimate, not locally calibrated crop need or an irrigation dose. Gross rain is not effective rain; soil storage, runoff and irrigation are excluded."
      }
    }
  ]
}
```

GET /v1/evidence/weather?latitude=13.14&longitude=78.13


HTTP 200; X-Request-ID: 23ad3400-95eb-4db5-8779-b737d58484ea.

```json
{
  "api_version": "1.0",
  "source": "open_meteo_forecast",
  "request_url": "https://api.open-meteo.com/v1/forecast?latitude=13.14&longitude=78.13&hourly=temperature_2m%2Cprecipitation%2Cet0_fao_evapotranspiration%2Csoil_moisture_0_to_1cm%2Cwind_speed_10m&daily=temperature_2m_max%2Ctemperature_2m_min%2Cprecipitation_sum%2Cet0_fao_evapotranspiration&forecast_days=14&timezone=UTC&timeformat=unixtime&temperature_unit=celsius&wind_speed_unit=kmh&precipitation_unit=mm",
  "fetched_at": "2026-10-30T16:53:15.840108Z",
  "is_stale": false,
  "data_status": "complete",
  "location": {
    "latitude": 13.14,
    "longitude": 78.13
  },
  "grid_location": {
    "latitude": 13.110721,
    "longitude": 78.11475
  },
  "attribution_text": "Weather data by Open-Meteo.com",
  "licence_url": "https://creativecommons.org/licenses/by/4.0/",
  "daily": {
    "time": [
      "2026-10-30T00:00:00Z"
    ],
    "values": {
      "temperature_2m_max": [
        28.8
      ],
      "temperature_2m_min": [
        18.9
      ],
      "precipitation_sum": [
        0.0
      ],
      "et0_fao_evapotranspiration": [
        4.44
      ]
    },
    "units": {
      "temperature_2m_max": "°C",
      "temperature_2m_min": "°C",
      "precipitation_sum": "mm",
      "et0_fao_evapotranspiration": "mm"
    }
  }
}
```

GET /v1/evidence/mandi?district=Kolar&commodity=Tomato


HTTP 503; X-Request-ID: 1c692df1-949d-4328-9390-db0121a46cdc.

```json
{
  "api_version": "1.0",
  "error": {
    "code": "missing_api_key",
    "message": "Agmarknet: AGMARKNET_API_KEY is not configured",
    "source": "Agmarknet",
    "retryable": false,
    "request_id": "1c692df1-949d-4328-9390-db0121a46cdc"
  }
}
```

GET /health/sources


HTTP 200; X-Request-ID: d3b758d4-6f71-4fe3-88d0-04e6cc2f92a6.

```json
{
  "api_version": "1.0",
  "sources": {
    "open_meteo_forecast": {
      "status": "available",
      "checked_at": "2026-10-30T16:53:15.839125Z",
      "error_code": null,
      "request_count": 1,
      "latency_ms": 827.9999999795109
    },
    "open_meteo_geocoding": {
      "status": "available",
      "checked_at": "2026-10-30T16:53:16.764672Z",
      "error_code": null,
      "request_count": 1,
      "latency_ms": 719.0000000409782
    },
    "open_meteo_flood": {
      "status": "available",
      "checked_at": "2026-10-30T16:53:17.948038Z",
      "error_code": null,
      "request_count": 1,
      "latency_ms": 1125.0
    },
    "nasa_power": {
      "status": "degraded",
      "checked_at": "2026-10-30T16:53:19.214202Z",
      "error_code": "partial_data",
      "request_count": 1,
      "latency_ms": 1186.9999999180436
    },
    "soilgrids": {
      "status": "degraded",
      "checked_at": "2026-10-30T16:53:22.143042Z",
      "error_code": "empty_data",
      "request_count": 1,
      "latency_ms": 2875.0
    },
    "agmarknet": {
      "status": "unconfigured",
      "checked_at": null,
      "error_code": "missing_api_key",
      "request_count": 0,
      "latency_ms": null
    }
  }
}
```

## Optional evidence contract

Plan now also includes optional_evidence_notes. Soil availability never gates deterministic weather tasks. NASA POWER evidence includes evidence_role=observation_cross_check. Its route and client accept only UTC dates from 1981-01-01 through seven days before the current UTC date; the conservative lag avoids requesting forecast/recent dates from a retrospective product. Null values remain possible inside this range. The visible app requests the completed week ending eight days ago and does not use these observations as forecast inputs. DATA_GOV_IN_API_KEY is the primary market environment variable, with AGMARKNET_API_KEY retained as an alias.

## Explanations, questions and traces

POST /v1/plans accepts language=en|hi|kn|te|ta|mr (default en). It adds agent_note and trace_id. Each dated action adds explanation_status, explanation_sources and the existing explanation text; unavailable generation leaves the deterministic reason intact. POST /v1/chat accepts question (1–2000 characters), plot (the same validated plan request) and language. It returns status=verified|unavailable, claims, facts, code-formatted facts, a trace_id, a visible note and the available structured plan. GET /v1/traces/{UUID} returns the compact execution summary; missing IDs return the project error envelope. See api-schema.json and AGENT.md for the complete contract and numeric limitations. No successful live-model example is available.

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
