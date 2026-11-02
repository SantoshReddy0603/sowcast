# Testing

## Environments and commands

Use Python 3.12 and Node 22. Create the Python environment, temporary databases, caches and build output outside the checkout. npm ci installs apps/web/node_modules; that directory is ignored. Do not copy private environment files or production databases into tests.

Install the API runtime lock plus editable dev extra. Setuptools accepts egg_info and --egg-base through pip config settings to place editable package metadata in an existing external directory. Python -B or PYTHONDONTWRITEBYTECODE prevents source bytecode artifacts.

Run from the repository root:

```sh
python -B -m pytest -c apps/api/pyproject.toml apps/api/tests -q --basetemp ../sowcast-tests -o cache_dir=../sowcast-cache/pytest
python -B -m ruff check --cache-dir ../sowcast-cache/ruff apps/api/src apps/api/tests
python -B -m mypy --cache-dir ../sowcast-cache/mypy --config-file apps/api/pyproject.toml apps/api/src
```

The parent of --basetemp must already exist. TEST_DATABASE_URL enables the PostgreSQL case on a dedicated local test server with permission to create/drop ephemeral child databases. Never use a production server. Without this setting the PostgreSQL test skips explicitly; SQLite still runs.

From apps/web:

```sh
npm ci
npm run lint
npm run typecheck
npm run build -- --outDir ../../../sowcast-web-dist
npm audit --audit-level=moderate
```

The output directory is outside the checkout. The server supports a separate DATABASE_URL, PORT and SOWCAST_UNAVAILABLE_SOURCE for isolated local runs. Private keys belong only in the server environment. GEMINI_API_KEY, GOOGLE_API_KEY and data.gov.in key paths remain UNVERIFIED when those variables are absent.

## Automated coverage

Source tests read recorded responses only from tests/recorded. Application code does not read them. Tests cover provenance, units, timestamp alignment, partial/null/empty fields, invalid payloads, retries, circuits and typed failures. Controlled clocks/transports exercise stale retention, coalesced refresh, hard expiry and timeouts. These are not claims that a remote service timed out during verification.

Agronomy tests cover every enabled catalogue parameter, stage boundaries/interpolation, district/reference-profile scope, missing inputs, stale suppression and evidence-specific reasons. Disabled parameters retain null values and typed insufficient_data. These checks do not establish field efficacy or independent correctness of every source citation.

Provider tests use deliberately constructed JSON/error responses and recorded weather. They cover schema conversion, bounded correction, quota retry/cooldown, retries on server errors and incomplete replies, malformed replies, evidence binding and adversarial quantities in six scripts. No fabricated provider success is used at runtime. These offline cases are separate from the successful deployed Gemini and voice tests; they do not measure language quality or field outcomes.

API/storage tests cover request IDs, validation/envelopes, rate limits/CORS, source health, schema equality, trace capability access/deletion, redaction/bounds, empty SQLite/PostgreSQL migrations, preservation of legacy records and database backup/restore protections.

## Browser checks

Set SOWCAST_WEB_URL to the running web app. Run scripts from an external working directory so screenshots/test-results remain outside the checkout. The script imports still resolve the approved development-only Playwright package from apps/web/node_modules.

Run browser.mjs, ask.mjs, reliability.mjs, district.mjs, climate.mjs, ragi.mjs, validation.mjs and freshness.mjs from apps/web/tests. Run outage.mjs against a separate web/API instance configured with SOWCAST_UNAVAILABLE_SOURCE=open_meteo_forecast. The normal source error path returns 503 and no invented plan. No public simulation endpoint exists.

Browser cases use real public-service requests for normal flows. Explicit request aborts and mutations of a real response exercise missing/stale/error states only inside tests. Those controlled cases must not be represented as natural remote failures. Voice-unavailable and permission-denied callbacks are simulated in these automated cases. Successful voice use was checked separately on the deployed app. Desktop 1280px and mobile 390px, keyboard flow, dark/reduced-motion and overflow checks are included. This is not a full accessibility conformance audit.

Climate, backtest and agent routes have separate expensive-route budgets. All requests still consume the general budget, and repeated requests to one class can receive 429. Retain that result and rerun after Retry-After rather than hide it or invent data. Provider availability and source outages can also affect live checks.

## Current verification results

The local API suite reports **371 passed, 1 skipped**: the PostgreSQL case skips when TEST_DATABASE_URL is absent. Ruff passes and mypy checks 54 source files. Web lint, strict types and production build pass; npm audit reports zero vulnerabilities. The 2 November 2026 rerun completed in 89.43 seconds and the Vite build in 8.00 seconds. An initial CLI subprocess timeout passed on an isolated rerun and on the subsequent full run; no source change was made to hide it.

Browser flows have been run successfully, and Gemini plan/chat and voice have been tested successfully on the deployed app. These are separate checks from the offline suite. The current local README captures use actual public-source responses for Kolar, 13.14, 78.13, on 2 November 2026: Plan shows 14 actions, a complete historical comparison and the evidence-only explanation state; Reliability shows seven leads for 29 August–27 October 2026. The screenshot browser reported no page errors. The captures do not claim to demonstrate deployed Gemini output.

Latest main GitHub Actions API and web jobs pass. The browser job is manual-only and was skipped. Scheduled Warm API jobs in the inspected history were skipped; the workflow is opt-in and its presence does not demonstrate a running keep-alive.

Application logs use structlog JSON on stderr. API records contain the server request ID, route template, method, status, source name and elapsed milliseconds. Source attempts record the source name, status or safe error code, attempt count and latency, inheriting the request ID. Raw paths, query strings, headers, bodies and provider payloads are excluded. Unhandled application errors return a fixed internal_error envelope without logging exception details. CLI evidence remains JSON on stdout. Run uvicorn with --no-access-log so its separate access logger does not print raw request targets. Logging behavior follows the context-variable guidance at https://www.structlog.org/en/stable/contextvars.html.

The optional recording script requires SOWCAST_DEMO_OUTPUT pointing outside the checkout. It records real app responses; it is not used as runtime evidence or an application fallback.

Validation tests cover forged district context through plan/chat, whitespace-only questions and canonical/nested sowing-date boundaries. Provider-wire tests count retries and corrections against shared two-request plan and six-request chat caps. Plan trace tests cover bounded inputs, missing values, source URL credential removal, rule versions, latency and cache paths. Rate tests prove budget isolation while preserving the general cap and 429 envelope. Logging tests verify API/CLI request-ID correlation and absence of raw private inputs. Browser validation/freshness cases use the existing error screens and exercise a held request to prevent duplicate Plan clicks.

A separate empty-database backtest command completed successfully in 6.165 seconds and produced seven leads. This is one local cold-recompute measurement, not a hosted timeout guarantee. Plan forecast_reliability, the Ask evidence-values list and provider retry cases have offline coverage. The fresh Plan/ Reliability screenshots and successful browser-flow checks provide separate UI evidence; neither is a substitute for provider quota or model-specific transport tests.
