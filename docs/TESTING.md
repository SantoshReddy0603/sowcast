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

Provider tests use deliberately constructed JSON/error responses and recorded weather. They cover schema conversion, bounded correction, quota retry/cooldown, retries on server errors and incomplete replies, malformed replies, evidence binding and adversarial quantities in six scripts. No fabricated provider success is used at runtime. Live model generation, non-English fluency and physical speech require separate verification.

API/storage tests cover request IDs, validation/envelopes, rate limits/CORS, source health, schema equality, trace capability access/deletion, redaction/bounds, empty SQLite/PostgreSQL migrations, preservation of legacy records and database backup/restore protections.

## Browser checks

Set SOWCAST_WEB_URL to the running web app. Run scripts from an external working directory so screenshots/test-results remain outside the checkout. The script imports still resolve the approved development-only Playwright package from apps/web/node_modules.

Run browser.mjs, ask.mjs, reliability.mjs, district.mjs, climate.mjs, ragi.mjs, validation.mjs and freshness.mjs from apps/web/tests. Run outage.mjs against a separate web/API instance configured with SOWCAST_UNAVAILABLE_SOURCE=open_meteo_forecast. The normal source error path returns 503 and no invented plan. No public simulation endpoint exists.

Browser cases use real public-service requests for normal flows. Explicit request aborts and mutations of a real response exercise missing/stale/error states only inside tests. Those controlled cases must not be represented as natural remote failures. Voice-unavailable and permission-denied callbacks are simulated; no microphone/audio success is claimed. Desktop 1280px and mobile 390px, keyboard flow, dark/reduced-motion and overflow checks are included. This is not a full accessibility conformance audit.

Climate, backtest and agent routes have separate expensive-route budgets. All requests still consume the general budget, and repeated requests to one class can receive 429. Retain that result and rerun after Retry-After rather than hide it or invent data. Provider availability and source outages can also affect live checks.

## Observed local results

Local results: the API suite reported 371 passed, 1 skipped in 37.52 seconds (the PostgreSQL case skips without TEST_DATABASE_URL), Ruff passed and mypy checked 54 source files. Web dependency install, lint, strict types and production build passed (1.88-second Vite build); npm audit found 0 vulnerabilities. The browser scripts (test:browser, test:district, test:climate, test:ragi, ask.mjs, reliability.mjs) were not run; they need both servers and live public sources. Results were produced with the commands in this file; tool caches are gitignored. The live Kolar requests recorded in docs/API.md returned weather/plan/flood/climate evidence, a previously computed backtest, protected trace read/delete and a typed induced source failure. Cached backtest retrieval was not timed as a cold recompute. Live Gemini output and market data are not covered by the recorded results. The numbers above are local results. The repository's GitHub Actions Checks workflow (web typecheck, lint and build; API mypy and tests) passes on main. Hosted behavior is not covered: the hosted free tier can return a retryable source error when Open-Meteo rate-limits its shared IP.

GitHub Actions definitions cover API lint/types/tests with PostgreSQL and web lint/types/build. The browser job is manual because it depends on live sources. Remote execution of the current branch is UNVERIFIED. Provider success, authenticated market data, physical speech, deployment TLS/persistence/cold starts and expert language/agronomy review remain unverified.

Application logs use structlog JSON on stderr. API records contain the server request ID, route template, method, status, source name and elapsed milliseconds. Source attempts record the source name, status or safe error code, attempt count and latency, inheriting the request ID. Raw paths, query strings, headers, bodies and provider payloads are excluded. Unhandled application errors return a fixed internal_error envelope without logging exception details. CLI evidence remains JSON on stdout. Run uvicorn with --no-access-log so its separate access logger does not print raw request targets. Logging behavior follows the context-variable guidance at https://www.structlog.org/en/stable/contextvars.html.

The optional recording script requires SOWCAST_DEMO_OUTPUT pointing outside the checkout. It records real app responses; it is not used as runtime evidence or an application fallback.

Validation tests cover forged district context through plan/chat, whitespace-only questions and canonical/nested sowing-date boundaries. Provider-wire tests count retries and corrections against shared two-request plan and six-request chat caps. Plan trace tests cover bounded inputs, missing values, source URL credential removal, rule versions, latency and cache paths. Rate tests prove budget isolation while preserving the general cap and 429 envelope. Logging tests verify API/CLI request-ID correlation and absence of raw private inputs. Browser validation/freshness cases use the existing error screens and exercise a held request to prevent duplicate Plan clicks.

A separate empty-database backtest command completed successfully in 6.165 seconds and produced seven leads. This is one local cold-recompute measurement, not a hosted timeout guarantee. Plan forecast_reliability, the Ask evidence-values list and provider retries on server errors and incomplete replies are covered by offline tests, lint and typecheck only; the browser scripts and the live Kolar flow have no recorded result for them.
