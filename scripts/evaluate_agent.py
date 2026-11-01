"""Post a fixed question set to a running /v1/chat and tally what the traces record.

The script reads no credentials. It sends only the question set to the API and
the per-response trace token to the matching trace URL. The summary is written
outside the checkout so measured results are never committed by accident.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = Path(__file__).with_name("agent_questions.json")
DEFAULT_OUTPUT = ROOT.parent / "sowcast-eval" / "agent_summary.json"
LANGUAGES = ("en", "hi", "kn", "te", "ta", "mr")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the agent question set against a running Sowcast API."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="API root URL")
    parser.add_argument("--questions", type=Path, default=QUESTIONS, help="question set JSON")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="summary JSON path; must be outside the checkout",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=7.0,
        help="seconds between requests; the server allows 10 chat/plan calls a minute",
    )
    parser.add_argument("--timeout", type=float, default=150.0, help="seconds per HTTP request")
    parser.add_argument("--limit", type=int, default=0, help="run only the first N questions")
    parser.add_argument(
        "--language", choices=LANGUAGES, action="append", help="restrict to a language (repeatable)"
    )
    return parser.parse_args(argv)


def call(
    method: str,
    url: str,
    body: dict[str, Any] | None,
    timeout: float,
    token: str | None = None,
) -> tuple[int, dict[str, Any], dict[str, str]]:
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status, raw = response.status, response.read()
            reply = {k.lower(): v for k, v in response.headers.items()}
    except urllib.error.HTTPError as exc:
        status, raw = exc.code, exc.read()
        reply = {k.lower(): v for k, v in exc.headers.items()}
    try:
        parsed = json.loads(raw) if raw else {}
    except ValueError:
        parsed = {}
    return status, parsed if isinstance(parsed, dict) else {}, reply


def load_questions(path: Path, languages: list[str] | None, limit: int) -> list[dict[str, Any]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    defaults = document.get("plot_defaults", {})
    items = []
    for entry in document["questions"]:
        if languages and entry["language"] not in languages:
            continue
        plot = {
            "latitude": entry.get("latitude", defaults.get("latitude")),
            "longitude": entry.get("longitude", defaults.get("longitude")),
            "crop": entry["crop"],
            "sowing_status": entry["sowing_status"],
        }
        items.append({**entry, "plot": plot})
    return items[:limit] if limit > 0 else items


def guardrail_outcome(value: Any) -> str:
    if isinstance(value, dict):
        return "passed" if value.get("passed") else "failed"
    return str(value) if value else "missing"


def retry_wait(headers: dict[str, str]) -> int:
    try:
        return min(90, max(1, int(headers.get("retry-after", "10"))))
    except ValueError:
        return 10


def run_question(base: str, entry: dict[str, Any], timeout: float) -> dict[str, Any]:
    record: dict[str, Any] = {
        "id": entry["id"],
        "language": entry["language"],
        "reviewed": bool(entry.get("reviewed")),
        "http_status": None,
        "status": "request_failed",
        "guardrail": "missing",
        "tools": [],
        "fallback_codes": [],
    }
    payload = {"question": entry["question"], "plot": entry["plot"], "language": entry["language"]}
    started = time.monotonic()
    try:
        code, answer, headers = call("POST", f"{base}/v1/chat", payload, timeout)
        if code == 429:
            wait = retry_wait(headers)
            time.sleep(wait)
            code, answer, headers = call("POST", f"{base}/v1/chat", payload, timeout)
    except (OSError, TimeoutError):
        record["fallback_codes"] = ["connection_error"]
        record["seconds"] = round(time.monotonic() - started, 2)
        return record
    record["http_status"] = code
    record["seconds"] = round(time.monotonic() - started, 2)
    if code != 200:
        record["status"] = f"http_{code}"
        record["fallback_codes"] = [f"http_{code}"]
        return record
    record["status"] = answer.get("status", "unknown")
    record["claim_count"] = len(answer.get("claims") or [])
    trace_id, token = answer.get("trace_id"), answer.get("trace_access_token")
    if not trace_id or not token:
        record["fallback_codes"] = ["trace_missing"]
        return record
    try:
        trace_code, reply, _ = call("GET", f"{base}/v1/traces/{trace_id}", None, timeout, token)
    except (OSError, TimeoutError):
        record["fallback_codes"] = ["trace_unreachable"]
        return record
    trace = reply.get("trace") if trace_code == 200 else None
    if not isinstance(trace, dict):
        record["fallback_codes"] = [f"trace_http_{trace_code}"]
        return record
    codes: list[str] = []
    if trace.get("error"):
        codes.append(str(trace["error"]))
    events = [e for e in trace.get("tools") or [] if isinstance(e, dict)]
    codes += [str(e["code"]) for e in events if e.get("code")]
    record["guardrail"] = guardrail_outcome(trace.get("guardrail"))
    record["tools"] = [str(e.get("name")) for e in events]
    record["fallback_codes"] = codes
    record["provider_requests"] = trace.get("provider_requests")
    return record


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    def tally(key: str) -> dict[str, int]:
        return dict(sorted(Counter(r[key] for r in records).items()))

    by_language: dict[str, dict[str, int]] = {}
    for language in LANGUAGES:
        subset = [r for r in records if r["language"] == language]
        if subset:
            by_language[language] = dict(sorted(Counter(r["status"] for r in subset).items()))
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "questions": len(records),
        "status": tally("status"),
        "status_by_language": by_language,
        "guardrail": tally("guardrail"),
        "tools": dict(sorted(Counter(t for r in records for t in r["tools"]).items())),
        "fallback_codes": dict(
            sorted(Counter(c for r in records for c in r["fallback_codes"]).items())
        ),
        "unreviewed_languages": sorted({r["language"] for r in records if not r["reviewed"]}),
        "results": records,
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output = args.output.expanduser().resolve()
    if output == ROOT or ROOT in output.parents:
        print("--output must be outside the checkout", file=sys.stderr)
        return 2
    questions = load_questions(args.questions, args.language, args.limit)
    base = args.base_url.rstrip("/")
    records = []
    for index, entry in enumerate(questions):
        if index:
            time.sleep(max(0.0, args.delay))
        record = run_question(base, entry, args.timeout)
        records.append(record)
        print(f"{entry['id']}: {record['status']}", flush=True)
    summary = summarize(records)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"summary written to {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
