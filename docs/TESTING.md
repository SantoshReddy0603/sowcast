# Testing

Run the commands in README from the repository root. Tests use a real Open-Meteo response under `tests/recorded/forecast.json`, with its request URL and fetch time in the adjacent metadata file. Runtime code never reads these files. Re-record only from a successful live response; do not synthesize weather values. Mutations of this recording exercise invalid schemas and units in isolated tests.

Client tests cover source provenance, units, time alignment, missing fields, retry policy, authentication failures and circuit opening. Cache tests cover request coalescing, fresh hits, stale flags, original fetch time and hard expiry during an outage. Coordinate tests reject invalid and non-finite input. Tests make no external calls. Live CLI verification is separate and requires network access.

Remaining verification includes additional crop calibration, live provider behavior, hosted deployment, load and remote CI execution.

## HTTP evidence verification

After editable installation, run checks from the repository root using README commands. API tests use httpx AsyncClient with ASGITransport, explicitly enter FastAPI lifespan, and inject MockTransport only at the upstream HTTP boundary. The success payload is the real recorded forecast under tests/recorded. Application code contains no mock response path.

API tests verify health without a source call, evidence and licence attribution, cache reuse, distinct request IDs, typed source failure with no leaked upstream details, and missing/non-finite/out-of-range coordinates without source calls. Source tests also reject null unit dictionaries. Tests exercise CLI error-envelope construction; a separate actual CLI run with an unreachable HTTPS proxy verifies nonzero exit, source name, retryability, request ID and no traceback. The source-failure API test checks the exact error contract, not just the status code.

Live verification used uvicorn on 127.0.0.1:8000 and GET /v1/evidence/weather?latitude=12.97&longitude=77.59. It returned HTTP 200 with real source values and X-Request-ID. GET /health returned 200. Live runs are separate from offline tests and are never substituted with recorded data. Deployment and load coverage remain absent. Backtest coverage is documented below. Agent, multilingual numeric guardrail and browser coverage are described below.


## Agronomy coverage

Pure-rule tests exercise boundary values, deterministic property loops, missing arguments, non-finite values and invalid inputs. Catalogue tests verify all six crops and enabled-citation/disabled-null invariants. Recorded-response API tests exercise plans for each crop, input rejection without an upstream call, explicit source failure, missing rainfall, stale-data suppression and growth-stage gating. Live verification is a separate actual POST to the running uvicorn server. These checks do not establish crop-specific calibration or field efficacy. No new test framework or fixture data was added; PyYAML is the only newly declared runtime dependency.


## Stage-specific reference water balance

Tests exercise every enabled Kc value against the researched table values, all four maize duration boundaries, development interpolation, reference-profile scope, stage validity intervals, Kc_end endpoint semantics, missing inputs, explicit FAO-reference selection, paddy/tomato management conditions and district filtering. Monotonicity loops cover rainfall/ET0 shortfall. Recorded-response API tests assert both computed amounts and the evidence-specific task text; the application never reads test recordings. A separate live Kolar request is recorded as an actual example in API.md. No field validation or district geospatial validation is claimed.

## Source and cache coverage

Recorded-response tests now cover geocoding, flood, NASA POWER and SoilGrids using actual responses and adjacent fetch metadata. POWER fill values remain null; SoilGrids' entirely null means report empty. Unit/schema mutations exercise rejection separately from recordings. No successful market fixture has been invented: market coverage is limited to missing-key handling and failure behavior until an authenticated run is possible.

Cache tests cover fresh reuse, expiry boundaries, concurrent stale refresh coalescing, original timestamps, hard stale retention, cancellation isolation and shutdown. Health tests assert that reading health makes no upstream request and that only requested sources acquire timestamps/counters. Contract tests compare the published OpenAPI snapshot, exercise version rejection, sowing_date echo/conflict validation and explicit unavailable crop water balance. Missing forecast coverage and saturated cache refresh capacity have regression tests. All tests are offline; the API.md examples and source behavior reports come from separate real requests.


## Browser checks

The Playwright development dependency exercises the app against separately running real API and Vite servers. The visible flow covers actual Kolar search, map selection, maize and sowing date, the real dated plan, evidence disclosure and SVG chart. A 390px viewport checks no document overflow; keyboard Tab enters the search field and button after navigation. A browser-aborted plan request checks error/retry. A separate API process with an unreachable HTTPS proxy produced a true upstream network failure; outage.mjs checked HTTP 503, source name, retryability, request ID and no replacement plan values.

Stale and missing-calendar-day states use an isolated mutation of an actual response within the browser test, never an application fallback or demo fixture. The chart must split the band across missing dates. Optional soil is requested live and missing values remain visible. Dark/reduced-motion preferences are exercised. Screenshots were visually inspected; this is not an exhaustive accessibility audit. No assertion is made about climate-normal comparison, which is explicitly unavailable.

NASA date tests reject pre-1981, recent and future requests before any upstream HTTP call. The real retrospective and five-location soil checks are recorded in DATA_SOURCES.md. DATA_GOV_IN_API_KEY was absent, so no market success is claimed.

## Agent checks

The agent tests use recorded weather inputs and deliberately constructed adversarial drafts. They cover batched explanations, corrected date/value failures, cache reuse, tool argument correction and newly registered tool facts, unavailable provider fallback, trace lookup/redaction/size and malformed provider envelopes. Guardrail cases cover native digits and rainfall, temperature, day and percentage unit words in English, Hindi, Kannada, Telugu, Tamil and Marathi, plus wrong units/date/place and unparsed numbers. No live model is called in tests and no successful provider recording has been fabricated. HTTP 429 and malformed-response tests are synthetic transport boundary tests.

With real local API and Vite servers running, node tests/ask.mjs from apps/web checks a mobile plot, live forecast, deterministic fallback, typed Ask and persisted tool trace. It verifies provider_unconfigured with no claims and no page errors. Speech recognition and audible synthesis require manual browser/device checks; headless verification does not establish those work.

The complete verified API suite passes 237 tests. Ruff and mypy pass for the current API source, strict web types and the production build pass, and the Plot/Plan, Ask and Reliability browser flows pass. These checks do not establish successful live model integration.

## Backtest verification

Real previous_runs.json and era5.json fixtures have adjacent request/fetch metadata. Offline tests check valid-time alignment, preceding-hour midnight boundaries, missing/full-day denominators, no default zeros, probability bounds, invalid units/times/values, typed API failures, concurrent coalescing, cross-instance persisted reuse, expired lease recovery, owner isolation, cached-result expiry and invalid CLI coordinates without tracebacks. Agent tests verify that backtest facts retain both source requests and the comparison window.

node tests/reliability.mjs from apps/web exercises the real local API and directly labelled second chart, desktop/mobile containment, error/retry, and isolated mutations of a live response for empty/stale rendering. Dark/reduced-motion checks report no page errors. Screenshots were visually inspected. Tests never read source recordings in application code or substitute a deterministic rain flag for a probability.

Quantity regressions reject all reported native-language word quantities, Roman numerals and matching numeric prose through both the strict gate and the actual regeneration/fallback loop. A closed per-language vocabulary limits model wording; unknown tokens fail closed. Numeric normalization is tested separately from the prose gate. Backtest revisions test inclusive 1 mm, paired-mask base rates and majority baselines, empty results, and Wilson interval reference values and symmetry. Browser checks compare both displayed definitions against the real HTTP response, including denominators and UTC/IST text. Local cold timings and their limits are in BACKTEST.md.

A subsequent real SoilGrids request returned HTTP 503 with source, retryability and request ID; the plan stayed available. The browser test now checks the UI against the actual response (values, nulls or a typed source failure), rather than assuming the earlier all-null response will remain true. Its response wait covers the configured source retry budget.

## Limits, storage and containers

Rate tests exercise shared plan/chat budgets, process-wide expensive budgets, sliding-window expiry, concurrent requests, CORS preflight/origin denial, forwarded-header resistance and the 429 envelope/headers before source work. A real one-request-budget server returned 200 then 429 with Retry-After=60 and the correct CORS/request-ID headers.

Migration tests create a truly empty SQLite file and a new ephemeral PostgreSQL database, apply Alembic revision 0001 twice, inspect tables/version, write/redact/read a trace and exercise owner-checked job/result persistence through separate repository instances. Existing SQLite traces are preserved. Production configuration rejects local storage, missing TLS mode and disabled TLS. The readiness error test confirms private driver details do not appear in a 503 response. TEST_DATABASE_URL must identify a dedicated test server whose role can create/drop databases; the tests never erase an existing named production database. No configured server means the PostgreSQL case skips explicitly.

The final local API run used TEST_DATABASE_URL against PostgreSQL 17.6 in Docker and reported 237 passed. Ruff passed; mypy checked 48 source files. pip check reported no broken requirements. Web strict types, ESLint and production build passed; npm audit reported zero vulnerabilities after the pinned minimatch 11.0.1 correction. These are local results, not a GitHub Actions run.

Docker Compose build produced both images. Compose up with wait reported database, API and web healthy. Image inspection confirmed API UID 10001:10001 and web UID 101. The web proxy returned a real-weather plan with 14 actions. Local API restart to /ready took 10.402 seconds. Host cold starts, cloud TLS and remote persistence are unverified. The API image includes packaged migration modules; the final stack uses PostgreSQL rather than unshared SQLite files.

Browser scripts accept SOWCAST_WEB_URL to exercise either Vite or the real Docker web proxy. All three flows passed against the containers, including current source values, mobile width, keyboard focus, missing/stale mutation cases and optional-soil response handling. The separate failure-switch API and Vite proxy passed the outage browser test using the actual error body; no fabricated values were returned. The outage assertion validates the source, retryability, request ID and message actually returned by the normal error envelope.

## CI and audit scope

checks.yml runs API lint/types/tests with an ephemeral PostgreSQL service and web types/lint/build on pushes and pull requests. The manually dispatched browser job calls real sources and may fail when they are unavailable; it never silently replaces responses. warm-api.yml is a separate opt-in health request. Both workflows were parsed locally but were not executed on GitHub. Render and Vercel files were parsed and checked against official documentation, not submitted to provider APIs.

A repository text scan excluded installed/build/runtime/scratch output and checked for developer filesystem paths, key-shaped material, private keys, authorship/process markers, unfinished-work markers and emoji. Python syntax and source comments were inspected; Ruff and ESLint check unused imports/variables. Runtime dependencies are explicitly declared/locked; async drivers and migration transitives are exercised through their owning libraries. Citation thresholds, source endpoint constants and map viewport bounds are intentional static configuration; runtime recordings remain confined to tests. These checks are not a formal security, accessibility or dead-code proof.

A real PostgreSQL-backed Ask request returned the unconfigured-provider answer with get_forecast and run_risk_assessment trace events. The same trace body was retrieved with HTTP 200 after restarting the API container. A subsequent real backtest returned HTTP 200 with 59 paired rain days. This verifies local container/database persistence, not hosted restart behavior.

Storage boundary tests also cover a real refused PostgreSQL connection after startup and representative driver authentication, TLS and timeout errors. Expected I/O/driver failures become sanitized storage_unavailable responses with matching request-ID headers; programming errors are not relabelled as database outages.
