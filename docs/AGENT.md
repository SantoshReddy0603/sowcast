# Evidence explanations

Rules decide dated actions, thresholds and calculations. Model output can add constrained explanations but cannot change those actions. This is decision support, not a substitute for local extension advice.

## Provider and limits

GeminiProvider calls the generateContent HTTPS endpoint directly through httpx. GEMINI_API_KEY or GOOGLE_API_KEY and an explicit GEMINI_MODEL come from the environment. No default model or second provider is configured. The key is sent in the x-goog-api-key header, never the URL. Explicit --env-file loading is optional; private files are not loaded automatically by the server.

A normal plan explanation uses one structured response. A schema or guardrail rejection permits one correction generation. The provider may retry an unhinted HTTP429 once after one second; Retry-After and Google RetryInfo delays suppress immediate retry when longer. The provider also retries once after one second on an HTTP 500, 502, 503 or 504 or a generation that did not finish normally, unless the stop reason is a safety, blocklist, prohibited-content, sensitive-data or recitation block; the retry consumes the same request budget. Final429 responses start a local cooldown. Each HTTP request has a 25-second timeout and five-second connect timeout. Successful explanation entries are bounded at 128 and keyed by plot, crop, language, sowing date, UTC day, rule/context/actions and numeric evidence; original fetch timestamps are excluded. Cache hits are verified again. One plan generation has a shared cap of two provider HTTP requests in total, counting retries and corrections. Chat has a shared cap of six provider HTTP requests across its four model iterations. The transport consumes the per-request budget immediately before each HTTP attempt; concurrent requests have independent budgets. Exhaustion preserves deterministic evidence and shows no unchecked claims. Unconfigured providers and verified cache hits issue no provider requests. Traces record the consumed count and cap.

The outgoing schema removes presentation metadata and unsupported complexity while local Pydantic bounds remain enforced. For the exact configured 2.5 Flash and Flash-Lite model identifiers, thinkingBudget is zero. Other models retain their defaults. Provider errors map to fixed safe local codes; raw provider error messages and credentials are not exposed.

Provider transport references: https://ai.google.dev/api/generate-content and https://ai.google.dev/gemini-api/docs/structured-output.

## Evidence and bounded execution

Chat accepts a question, plot and one of en, hi, kn, te, ta or mr. Forecast and deterministic assessment execute first. The loop permits four model iterations and eight total evidence operations including those first two, with an 18-second deadline per operation and a 100-second model-loop deadline. Structured errors and empty results are passed back for correction. Exhaustion returns available structured evidence without accepted model claims.

Tool results go back to the model with a payload cap: the provider refuses a request body over 128000 bytes with the safe code context_too_large. The full run_risk_assessment plan is not sent back: the model receives only its status and, when present, its error code and retryable flag, plus the citable facts that code extracts from the plan. Available operations are get_forecast, get_soil, get_mandi_prices, run_risk_assessment, get_backtest and get_flood_signal. Forecast/risk/soil/flood/backtest use the validated plot; market arguments require district and commodity strings. Soil is optional; flood output is river discharge rather than field flood probability. Market values need a configured data.gov.in key. The GFS/ERA5 comparison uses the same backtest service as the API and CLI.

Sowing-timing questions are answered from several operations: the assessment and backtest results supply forecast rainfall, evidence facts for candidate days and the GFS/ERA5 agreement facts. The model does not recommend a sowing date, because the catalogue does not turn week bounds into dates and the onset rainfall, sowing temperature and soil readiness parameters are disabled. For ragi and tur no crop-water need is estimated.

Each claim is bound to evidence from the current request context. Numeric quantities, dates, units and location bindings are checked after normalizing supported scripts and unit words. Code renders values. A closed vocabulary rejects numeric prose, unknown words and unsupported characters in the six languages. One rejected draft may be regenerated, after which the response falls back to structured evidence. This conservative boundary does not prove the meaning of arbitrary prose or multilingual fluency; explanations can be generic and cannot replace deterministic reasons.

## Traces and privacy

SQLAlchemy stores bounded summaries in local SQLite or the configured PostgreSQL database. GET and DELETE /v1/traces/{UUID} require Authorization: Bearer with the trace_access_token issued in the creating response. Missing/wrong tokens and unknown records return the same 404 envelope. Deletion returns 204. The server stores a SHA-256 digest, never the raw capability; the browser keeps capabilities in memory and does not render them. UUID knowledge alone grants no access. Legacy records without digests remain inaccessible over HTTP.

Plan traces also retain the rule version, resolved coordinates, execution latency and at most 64 input references, including null values. Each reference contains the field, unit, value, valid/fetch times, stale flag and source URL without query or credentials. The total reference count makes truncation explicit. Plan latency includes source, rule and explanation work up to persistence; storage commit time is excluded. Cache hits and unavailable explanations retain these fields. The UI adds no new trace fields.

Traces contain operation names, validated arguments, coordinates, milliseconds, safe error codes and guardrail/cache outcomes. Strings are capped at 2,000 characters, encoded records at 64,000 bytes and retained records at 1,000. Raw questions, full source payloads, model drafts and private reasoning are not stored. Secret-shaped content is redacted. These capabilities do not provide account authentication or prove plot ownership.

## Evaluation script

scripts/evaluate_agent.py posts the 42 questions in scripts/agent_questions.json (English plus hi, kn, te, ta and mr) to a running /v1/chat, reads each trace with its own access token and writes a JSON tally of status, guardrail outcome, tool names and fallback codes. The summary goes outside the checkout (default ../sowcast-eval/agent_summary.json). The script reads no credentials; the server needs GEMINI_API_KEY and GEMINI_MODEL for answers, and without them every question reports provider_unconfigured. Questions in languages other than English are unreviewed by fluent readers. The default 7-second delay keeps under the server's 10 agent calls a minute. Measured results are published only after a complete run with enough provider quota; none are published yet.


## Verification limits

Live Gemini generation and authenticated market requests are UNVERIFIED without configured credentials and usable quota. Offline constructed drafts and recorded weather test the boundaries but do not establish live provider success. Independent language review, agronomic calibration, microphone capture, audible replies, physical-phone behavior and hosted deployment remain unverified. Browser voice may use a remote speech service; transcripts remain editable before submission, and typed input remains available when speech is unavailable or permission is denied.
