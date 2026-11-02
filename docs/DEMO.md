# Live demonstration

Web: https://sowcast-web.onrender.com. API: https://sowcast-api-820y.onrender.com. Gemini plan/chat, voice and browser flows have been tested successfully. Check current availability before starting.

## Pre-demo checklist

- Use the normal local or deployed API with SOWCAST_UNAVAILABLE_SOURCE empty. Confirm /health returns 200 and /ready returns ready. Request readiness manually well before starting so a sleeping host can wake before the demonstration.
- Set the model key and exact model name in the API environment only if you can verify current provider access and quota in the provider console. Retries and corrections share a total cap of two provider requests per plan; chat has a six-request provider cap. If no key is available, explicitly demonstrate the visible unavailable state and structured tool trace; do not describe it as a successful model answer.
- Precompute the actual demo plot with python -m sowcast backtest --latitude 13.14 --longitude 78.13 --scheduled using the API's DATABASE_URL or local storage paths. Confirm the window, paired counts and freshness in Reliability. A new UTC day creates a new cache key.
- Confirm Open-Meteo quotas and current /health/sources status. Soil is optional and may be null or unavailable. NASA is delayed retrospective evidence. Neither absence blocks weather tasks. If forecast evidence is down, show the typed failure honestly and retry later; do not substitute a source recording into the application.
- Prepare a separate local failure API on port 8002 and a separate web proxy on port 5174, leaving the normal app intact. The shell-independent Python command below injects the switch only into that child process. It is intentionally not a public URL toggle.

```sh
python -c "import os; os.environ['SOWCAST_UNAVAILABLE_SOURCE']='open_meteo_forecast'; os.environ['PORT']='8002'; from sowcast.__main__ import main; main()" serve
```

For the separate web proxy, run from the repository root in another terminal:

```sh
python -c "import os,subprocess; e=os.environ.copy(); e['SOWCAST_API_TARGET']='http://127.0.0.1:8002'; subprocess.run('npm --prefix apps/web run dev -- --port 5174', shell=True, env=e, check=True)"
```

The command text is fixed and contains no interpolated user input. On exit, the normal environment is unchanged. Shut down these two demo processes afterwards. A server configured with production PostgreSQL still uses its configured database for traces; the source switch does not erase data.

## Two to three minutes

| Time | Action and statement |
| --- | --- |
| 0:00–0:30 | In Plot, type latitude 13.14 and longitude 78.13, let Kolar resolve automatically, select maize, and choose the actual sowing status. Use a real sowing date only if known; otherwise keep not yet sown. Submit. State that all weather values came from the source attached to this plan. |
| 0:30–1:00 | In Plan, open Why this task? and point to the forecast inputs, rule version and citations. Show the fetch time in the section footer. If crop-water context is missing, show that it is unavailable rather than inventing a stage. Note that ragi and tur currently have no crop water-balance rule. |
| 1:00–1:35 | Open Ask and submit a short question such as “What evidence should I check?” Open Agent trace. Show the actual forecast and risk-assessment tool statuses and latencies, plus the guardrail result. If generation is configured, show only what passed. If unavailable, show the explicit note and explain that deterministic tasks remain. Voice is optional and must not be claimed working unless just exercised successfully. |
| 1:35–2:10 | Open Reliability. Read the current GFS model window and paired sample counts. Switch between >0 mm and ≥1 mm, show the ERA5 base rate and retrospective majority baseline, and note the approximate interval. State that no lead ranking is established and that UTC days run 05:30–05:30 IST. These scores do not measure the plan's best-match blend. |
| 2:10–2:40 | Open the isolated failure web at http://127.0.0.1:5174, select the plot and request a plan. Show the typed source-unavailable error and request ID, with no replacement weather or actions. The configured transport made no upstream call. Return to the normal app to show its independent functioning. |
| 2:40–3:00 | State: reliability shown for one location and window so far; decision support does not replace extension officers. |

## Failure fallback

If place search fails, use caller-entered coordinates. If soil or NASA fails, show its optional status and keep the weather plan. If the forecast fails, do not make a field recommendation; demonstrate error/retry and use the separately precomputed Reliability page only when its real saved window is available. If backtest sources fail on a cold request, show the typed failure; do not fabricate a score. If Gemini is unconfigured or quota-limited, show the deterministic plan and trace with the real error. Screenshots and recordings are documentation/test evidence, not application fallback data.
