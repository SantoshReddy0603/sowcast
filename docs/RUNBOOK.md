# Operations

## Request limits and CORS

Budgets are sliding 60-second windows in each API process. Defaults: 120 general requests per peer IP; 10 combined plan/chat requests per IP and process; 5 backtest requests per IP and 10 per process; 15 climate-normal requests per IP and 20 per process. Climate has a separate budget because the Plan view requests it on each mount and retry. These allowances cover repeated cached comparisons without consuming backtest or model budgets. All routes still consume the shared general budget. SOWCAST_RATE_LIMIT, SOWCAST_AGENT_LIMIT, SOWCAST_BACKTEST_LIMIT, SOWCAST_AGENT_GLOBAL_LIMIT SOWCAST_BACKTEST_GLOBAL_LIMIT, SOWCAST_CLIMATE_LIMIT and SOWCAST_CLIMATE_GLOBAL_LIMIT override these positive integers. /health and OPTIONS are exempt. /ready is a normal limited database probe. The bounded counter map refuses new buckets when full. Denied requests return 429 with Retry-After, retryable=true and the current request ID. They do not start provider or source work.

Counters reset on restart and do not coordinate workers or hosts. Shared gateways/NAT can share a client budget. The server does not trust arbitrary forwarded headers. This is not account-level abuse prevention. Model quotas vary; lower the global agent budget to allow for regeneration and HTTP retries. Rate limits do not guarantee a provider's free quota.

CORS_ORIGINS is a comma-separated list of exact HTTP origins without paths or wildcards; empty means no cross-origin grant. Credentials are not enabled. Allowed methods are GET/POST/DELETE; allowed request headers include Content-Type and Authorization. X-Request-ID and Retry-After are exposed. Same-origin Vite and Docker proxies do not require a permissive CORS policy.

## Storage

DATABASE_URL takes precedence for deployed storage and must identify PostgreSQL when SOWCAST_ENV=production. Use a direct asyncpg-compatible connection URL with sslmode=require; certificate validation is enabled. Do not include libpq-only channel_binding parameters. Without DATABASE_URL, local SQLite uses SOWCAST_TRACE_DB and SOWCAST_BACKTEST_DB. Existing SQLite rows are preserved by revision 0001; traces gain a retention timestamp. SQLAlchemy is used for records and Alembic for schema versions. Startup upgrades under a database lock before readiness succeeds. python -m sowcast migrate performs the same idempotent upgrade explicitly.

Writes use SQLite immediate transactions or PostgreSQL transaction advisory locks. Owner/expiry checks protect backtest leases. Summary retention is 128 records; trace retention is 1,000 records with a 64,000-byte record limit. Backtest results expire after one day and leases after five minutes. Database connections are closed after each transaction rather than held idle. /ready checks both storage repositories; /health checks only the process and makes no upstream request. Back up before upgrading: automatic destructive downgrades are deliberately refused. Local SQLite files are not automatically copied to hosted PostgreSQL; retain/export any local records you need before switching DATABASE_URL.

## Hosted database choice

Official pages were opened on 2026-10-31. Limits may change; recheck before creating services.

| Provider | Free allowance and limits | Use here |
| --- | --- | --- |
| [Neon](https://neon.com/pricing) | 1 GB/project, 100 CU-hours/month/project, up to 2 CU; scales to zero after five idle minutes. Limited recovery history: up to six hours or 1 GB of changes. | Selected for a hosted PostgreSQL independent of the API filesystem. |
| [Supabase](https://supabase.com/pricing) | 500 MB database, 5 GB egress, two active projects; pauses after one inactive week. | Alternative, not provisioned or tested here. |
| [Render](https://render.com/pricing) and [free limits](https://render.com/docs/free) | Free PostgreSQL expires after 30 days, then has a 14-day upgrade grace period before deletion. | Not selected for durable demo records. |

No hosted account or database was created. Local PostgreSQL migration and API-container-restart persistence tests do not verify a provider's network, quota, backup or availability behavior. Free services have no asserted production SLA. Export important records using your provider's backup/export interface; do not rely on the small free recovery window.

## Deployment preparation

The selected path is Render Free for the API, Neon for PostgreSQL and Vercel Hobby for the static web build. [Render Free](https://render.com/docs/free) provides 750 instance-hours per workspace/month and spins down after 15 idle minutes; its documentation estimates about one minute to wake. Its free API filesystem is ephemeral. [Fly.io pricing](https://fly.io/docs/about/pricing/) says new organizations have no ongoing free tier; the trial ends after two runtime hours or seven days. Render therefore meets the requested ongoing free API option. [Vercel Hobby](https://vercel.com/docs/plans/hobby) is restricted to personal, non-commercial use. Open-Meteo's free service also has non-commercial restrictions. Re-evaluate plans before any commercial use. These pages were read on 2026-10-31.

Nothing has been deployed. When you are ready, perform these steps yourself:

1. Create a Neon Free PostgreSQL project in a suitable region. Copy its direct connection URL; set DATABASE_URL in the API service secret settings. Use the asyncpg-compatible scheme postgresql+asyncpg and sslmode=require. Remove channel_binding from the URL if the provider included it. Certificate validation remains enabled. Do not put credentials into the repository or web variables.
2. In Render, create a Blueprint from render.yaml when the repository is available to you. Choose the free web-service plan. Auto-deploy is off; creating/applying the Blueprint still performs the initial deployment, so do this only when you intend to deploy. Supply DATABASE_URL, SOWCAST_ENV=production and CORS_ORIGINS containing the exact Vercel production origin. Supply GEMINI_API_KEY and GEMINI_MODEL only if you have verified provider access; DATA_GOV_IN_API_KEY is optional. Leave SOWCAST_UNAVAILABLE_SOURCE unset. Render sets PORT. Startup migrates before serving requests. /health is the configured host check; /ready is the manual database readiness check.
3. In Vercel, import apps/web as the project root, use Node 22, npm ci, npm run build, and dist. Set the public build variable VITE_API_BASE_URL to the Render HTTPS origin without a trailing slash. It contains no key. Rebuild after changing this variable. apps/web/vercel.json supplies routing and response headers. Add the resulting exact origin to Render CORS_ORIGINS; do not use a wildcard. Preview URLs need separate explicit origins if you want previews to call the API.
4. Check /health and /ready, then submit the actual plot, inspect source freshness, ask a question and inspect its trace, and open Reliability. Verify the new server’s persisted rows survive an API restart. Hosted networking, TLS and cold-start behavior have not been exercised here; local database/container tests do not establish those results.
5. Precompute the demo plot with python -m sowcast backtest --latitude 12.97 --longitude 77.59 --scheduled in an environment using the same DATABASE_URL. This reads and writes the shared backtest summary. Confirm current paired counts in the web view.

The opt-in warm-api.yml workflow runs every ten minutes when repository variable SOWCAST_KEEP_ALIVE=true and SOWCAST_API_URL is the public HTTPS origin. It only requests /health, not sources or the database. Set the boolean false or remove it to stop. Scheduled Actions are best effort, can be delayed, and may be disabled on inactive repositories; they do not guarantee an always-warm free host. Continuous uptime consumes Render's instance-hour allowance. /ready is intentionally not the periodic probe, because repeatedly querying Neon can prevent database scale-to-zero and consume its compute allowance. Warm /ready manually before a demo.

Local Docker restart-to-readiness measured 10.402 seconds, including the restart command and PostgreSQL-backed readiness. This is not a Render or Neon cold-start measurement. No remote cold-start measurement is possible without deploying. The earlier real local backtest recompute measurements are in BACKTEST.md.

## Local containers

Set POSTGRES_PASSWORD in the shell or a local untracked .env file to a new URL-safe hexadecimal password. Docker Compose reads .env; the Python CLI loads it only when explicitly passed `--env-file .env`. Run docker compose build, then docker compose up -d --wait. Open http://127.0.0.1:8080; the web proxy reaches the API at api:8000. API and web run as UID 10001 and 101 respectively; PostgreSQL runs as postgres. All base images are pinned by digest. API dependencies and web dependencies are locked. No credentials are build arguments or image content. Keep .env files out of build contexts.

Use docker compose stop to stop while preserving the database volume. Do not remove the volume unless you intend to erase local records. If you rotate POSTGRES_PASSWORD, update the existing database role password as well as the container environment; changing the environment alone does not change an initialized database role.

## Source outage and demonstration switch

SOWCAST_UNAVAILABLE_SOURCE is empty by default. Set it to exactly one source identifier: open_meteo_forecast, open_meteo_previous_runs, open_meteo_archive, open_meteo_geocoding, open_meteo_flood, nasa_power, soilgrids or agmarknet. Restart the API so the selected source's in-memory caches start empty. That transport reports unavailable and raises source_unavailable with retryable=true and the normal source/request-ID envelope before any upstream request. Other sources are untouched; no data is invented. The key-gated mandi client still reports its missing key first if no key is configured.

For the demo, use open_meteo_forecast in a separate local API process. A real call returned HTTP 503, source Open-Meteo forecast, retryable=true and request ID d9361fbd-5d8a-4ad9-8393-dc05df575406; the source attempt count remained zero. Remove the variable and restart to recover. This switch is controlled by server configuration, not by a public query parameter. Never leave it enabled after a demo. For natural upstream outages, keep missing/stale flags visible, retry within quota, and avoid making a field recommendation from absent evidence.

## Keys and recovery

Rotate a provider or market key in server secret settings, restart, and check configuration status without printing the value. Never add a model key to VITE_API_BASE_URL or any frontend variable. Traces are bounded and redacted, but include coordinates and district; there is no account authentication or plot ownership. Trace reads/deletions now require the separate response access token; a UUID alone grants no access. Keep this prototype limited to appropriate users until account controls are implemented. Inspect /health/sources to distinguish unconfigured, uncalled, degraded and unavailable sources; it never triggers probes.

## Trace retention and deletion

The database retains the newest 1,000 execution summaries, each at most 64,000 encoded bytes. There is no automatic age expiry. A response token authorizes reading/deleting only its trace; Ask exposes deletion. Losing that in-memory token removes browser access, but does not itself erase the server row. Legacy summaries without digests are unavailable through HTTP. Coordinate/district metadata remains private operational data. Deleted summaries can still exist in an earlier backup until the operator expires that backup; restoring it can reintroduce them. Do not collect identifiable farmer records with this prototype. A production retention schedule and account ownership remain required.

## SQLite backup and restore

Run from the project root using the installed API environment. These commands use SQLite's consistent backup API, include committed WAL data, verify integrity, and refuse every existing destination. They do not copy environment files or keys.

```powershell
python -m sowcast backup --source .sowcast/traces.sqlite3 --destination .sowcast/traces-backup.sqlite3
python -m sowcast restore --source .sowcast/traces-backup.sqlite3 --destination .sowcast/traces-restored.sqlite3
```

Repeat for the configured backtest database. Restoring writes a separate new file; it does not replace the running database. Stop the API before explicitly changing SOWCAST_TRACE_DB/SOWCAST_BACKTEST_DB to the inspected restored file. Keep snapshots private with restricted filesystem permissions, choose a retention period and remove expired copies. This local utility does not back up PostgreSQL: use the hosting provider's database tools, then rehearse hosted restoration separately. A local SQLite snapshot/restore rehearsal is recorded in TESTING.md.

Application logs use structlog JSON on stderr. API records contain the server request ID, route template, method, status, source name and elapsed milliseconds. Source attempts record the source name, status or safe error code, attempt count and latency, inheriting the request ID. Raw paths, query strings, headers, bodies and provider payloads are excluded. Unhandled application errors return a fixed internal_error envelope without logging exception details. CLI evidence remains JSON on stdout. Run uvicorn with --no-access-log so its separate access logger does not print raw request targets. Logging behavior follows the context-variable guidance at https://www.structlog.org/en/stable/contextvars.html.
