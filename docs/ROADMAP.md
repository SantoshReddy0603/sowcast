# Remaining work

## Current delivery

The web app is available on Render at https://sowcast-web.onrender.com; its API is https://sowcast-api-820y.onrender.com. Gemini plan/chat, voice and browser flows have been tested successfully. Latest main API/web GitHub Actions jobs pass; the manual-only browser job was skipped.

The README describes the current setup and supported scope. Further work below extends coverage rather than describing those completed checks as missing.

## Product and data

Obtain crop-specific ragi/tur water coefficients and stage lengths from readable official sources before enabling those rules. Broader sowing onset, heat/cold, GDD and waterlogging thresholds remain disabled where evidence is absent. Verify regional scope and stage applicability with Karnataka extension specialists; no field efficacy study has been performed.

SoilGrids reliability in the target districts is unresolved. A field soil-test input and provenance workflow would be preferable to treating modelled means as measured soil. NASA remains an observation cross-check, not a forecast. Agmarknet authenticated responses and price units need a real key/request. The 1991–2020 ERA5 calendar-day comparison is implemented; independent station-normal comparison and spatial calibration remain unavailable. Backtest uncertainty needs paired temporal methods and station validation before comparative skill claims.

## Operations

Account authentication and plot ownership remain unimplemented. Trace reads/deletions now require per-response bearer tokens with only token digests stored; UUIDs alone grant no access. The bounded retention and deletion policy is documented in RUNBOOK.md. A production age-based retention schedule and backup expiry policy remain operator decisions before collecting personal farm records. Process-local limits and caches do not coordinate across hosts; use a shared limiter when scaling. Database job locks are shared only through the same PostgreSQL instance.

Add provider/load and failure-recovery tests under deployment conditions, hosted PostgreSQL backup/restore rehearsal, dependency/image refresh and an independent accessibility audit. Local SQLite backup/restore, keyboard entry, mobile layouts and missing/denied browser-speech fallback have automated checks; these do not replace device and assistive-technology review. Keep source attribution and verified citations with every enabled rule. Do not treat a green test suite as proof of safe agronomic advice.
