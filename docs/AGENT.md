# Evidence explanations

Rules produce the dated tasks. The agent can add explanations and answer questions using retrieved evidence; it does not change rule actions, thresholds or calculated metrics. This is decision support, not a replacement for local extension advice.

## Provider and quota

`GeminiProvider` uses direct `httpx` HTTPS requests to `https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent`. Set `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) and `GEMINI_MODEL` in the process environment. There is no default model and no automatic `.env` loading. Keys travel in `x-goog-api-key`, never URLs. The provider protocol permits a future second implementation; no second provider is configured.

All plan explanations share one structured JSON response. The success path uses one generation. A failed guardrail or schema check permits one correction generation; HTTP 429 permits one retry after one second per generation. Each HTTP call has a 25-second timeout with a five-second connect timeout. Input JSON is limited to 120,000 bytes and response content to 100,000 bytes after receipt. The response limit does not bound network download memory. Non-200, incomplete, malformed and unconfigured responses degrade to unchanged deterministic tasks with a visible note. Drafts that fail numeric, vocabulary or schema checks are not returned. These checks do not establish arbitrary sentence semantics.

Successful explanations have a process-local cache, capped at 128 entries. Its identity includes plot coordinates, crop, language, sowing date, UTC calendar day, rule version, agronomy context, dated actions and numeric evidence. Fetch timestamps are excluded from the key. A changed rule action or evidence value invalidates reuse. Cached claims pass the guardrail again. Restarting the process empties this cache.

The transport follows Google's [generateContent API](https://ai.google.dev/api/generate-content) and [structured output documentation](https://ai.google.dev/gemini-api/docs/structured-output). The handwritten loop uses a JSON tool-call envelope, rather than Google's native function-call transport. No SDK or orchestration library is installed.

## Tools and budgets

`POST /v1/chat` takes a question, a validated plot matching the plan request contract, and language (`en`, `hi`, `kn`, `te`, `ta`, `mr`). Forecast and deterministic risk assessment run first. The loop then permits four model iterations and eight total tool executions, including the initial two. Each tool has an 18-second deadline; model iterations have a shared 100-second deadline after the initial tools. Provider quota retries remain within these deadlines. Invalid arguments, upstream failures, unavailable services and timeouts are structured results; the next model iteration receives these results with correction instructions. Empty source results retain their missing-data status. Exhaustion returns no model claims and includes the available structured plan.

| Tool | Arguments and behavior |
| --- | --- |
| `get_forecast` | No arguments; validated plot coordinates only. |
| `run_risk_assessment` | No arguments; validated crop and agronomy context only. |
| `get_soil` | No arguments; optional modelled soil evidence. |
| `get_flood_signal` | No arguments; river discharge, not plot flood risk. |
| `get_mandi_prices` | Required district and commodity strings, each at most 100 characters; Karnataka only. |
| `get_backtest` | No arguments; shared fixed-lead GFS versus ERA5 backtest for the validated plot. |

Plan inputs, subsequent fresh forecast/discharge outputs and eligible backtest summary metrics receive run-scoped fact IDs. Backtest facts include the comparison window, use its end date as the binding date, and link both source requests; they are window metrics rather than daily measurements. The model receives these IDs with date, location, unit, value, source URL and fetch timestamp. Missing and stale values are not numeric facts. Soil lacks a measured date and market price units remain unverified, so those tools currently provide context and availability only; their numeric values cannot be cited through the guardrail. NASA observations are not an agent forecast tool.

## Verification and rendering

Each explanatory claim carries an evidence ID, date and exact requested coordinates. The verifier binds all three to a fact from this run, normalizes Unicode decimal digits and unit aliases for the six languages, and compares parsed quantities exactly using decimal arithmetic. Native-script aliases cover rainfall, Celsius temperature, days and percentages. The numeric helper checks digit quantities and unit aliases. The application gate additionally forbids all quantities in explanatory prose, even when they match evidence. It checks raw Unicode numeric characters before normalization and permits only an explicit nonnumeric vocabulary for the selected language. Unknown words, unsupported scripts/characters, spelled quantities and units fail closed. The provider receives that vocabulary, can regenerate once, and otherwise returns no prose. This deliberately limits explanatory fluency. It is not a proof of arbitrary sentence semantics; the model cannot alter the structured rule actions.

One correction includes the discrepancies. A second failure returns structured tasks without the draft. Plan output requires exactly one nonempty claim for every action date before any explanation is accepted. Rules and deterministic reasons remain in the response regardless of provider availability.

Numbers and measurement labels beside answers are rendered by code from facts; matching numeric model prose is rejected rather than displayed. Native digits are selected by language; dates use code-owned calendar formatting. The model writes explanatory sentences. Existing deterministic plan reasons remain English. Unit symbols are stable scientific labels. No claim is made that the entire application interface is translated.

## Traces and privacy

SQLAlchemy persists compact execution summaries through DATABASE_URL, or local SQLite at SOWCAST_TRACE_DB (default .sowcast/traces.sqlite3). Alembic revision 0001 upgrades storage before serving requests. Hosted deployment requires PostgreSQL/asyncpg with certificate-validated TLS; local SQLite uses aiosqlite. `GET /v1/traces/{UUID}` returns a trace or a typed 404/422. Traces contain tool names, validated arguments, requested coordinates, milliseconds, status/error codes, cache use and guardrail results. Raw questions, source payloads, model drafts and private reasoning are not stored. Secret-named fields and URL key/token parameters are redacted; strings are capped at 2,000 characters, encoded records at 64,000 bytes and retained records at 1,000. This is a local prototype endpoint with no authentication. Trace IDs act as lookup capabilities; keep this service private until access control exists. Plot coordinates and district names remain in traces.

Ask offers typed input, optional browser speech recognition and optional speech synthesis. Audio processing depends on the browser and may use its remote speech service. Nothing is submitted automatically: the transcript can be edited first. Missing browser support or denied microphone access leaves typed input available. Actual microphone capture and audible speech were not verified in this headless environment.

## Verification limits

No Gemini key/model is configured in the verification environment. No live generation or successful model-response recording exists. Recorded weather responses exercise API integration. Constructed adversarial drafts exercise guardrails, regeneration, caching and tool correction; synthetic HTTP error/malformed-envelope inputs exercise the provider boundary. These are explicitly test inputs, not claimed provider recordings or application fallback data. A successful Gemini wire response, multilingual explanation quality and spoken replies still require a configured provider and interactive browser check.
