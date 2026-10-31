import asyncio
import hashlib
import json
from collections import OrderedDict
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from sowcast.agent.provider import Provider, ProviderError
from sowcast.agent.tools import PlotContext, ToolCall, ToolRunner
from sowcast.agronomy.assessment import Plan
from sowcast.agronomy.catalogue import Catalogue
from sowcast.guardrails.claims import Claim, Fact, verify
from sowcast.guardrails.prose import vocabulary
from sowcast.i18n.render import Language, measurement
from sowcast.sources.services import SourceServices
from sowcast.storage.traces import TraceStore


class Draft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claims: tuple[Claim, ...] = Field(default=(), max_length=30)
    tools: tuple[ToolCall, ...] = Field(default=(), max_length=6)


class Answer(BaseModel):
    api_version: Literal["1.0"] = "1.0"
    trace_id: str
    language: Language
    status: Literal["verified", "unavailable"]
    claims: tuple[Claim, ...] = ()
    facts: tuple[Fact, ...] = ()
    formatted_facts: dict[str, str] = Field(default_factory=dict)
    note: str
    plan: Plan | None = None


def plan_facts(plan: Plan) -> dict[str, Fact]:
    facts: dict[str, Fact] = {}
    for index, action in enumerate(plan.actions):
        for item in action.inputs:
            if item.value is None or plan.evidence.is_stale:
                continue
            identifier = f"day{index}:{item.field}"
            facts[identifier] = Fact(
                id=identifier,
                date=action.date.isoformat(),
                latitude=plan.location.latitude,
                longitude=plan.location.longitude,
                value=item.value,
                unit=item.unit,
                source_url=item_source(plan),
                fetched_at=plan.evidence.fetched_at.isoformat(),
            )
    return facts


def item_source(plan: Plan) -> str:
    return plan.evidence.request_url


def prompt_facts(facts: dict[str, Fact]) -> list[dict[str, Any]]:
    return [
        fact.model_dump(exclude={"source_url", "supporting_urls", "fetched_at"})
        for fact in facts.values()
    ]


def tool_facts(name: str, result: dict[str, Any]) -> dict[str, Fact]:
    if name == "get_backtest":
        summary = result.get("backtest")
        if not summary or summary.get("is_stale"):
            return {}
        facts = {}
        for score in summary["scores"]:
            labels = {
                "temperature_mae_c": (
                    "temperature average absolute error; "
                    f"n={score['temperature_pairs']} hourly pairs"
                ),
                "rain_correct_days": (
                    f"rain agreement (>0 mm), correct days; n={score['rain_pairs']} paired days"
                ),
                "rain_pairs": "paired rain days (>0 mm)",
                "rain_accuracy": f"rain agreement (>0 mm); n={score['rain_pairs']} paired days",
            }
            entries = [
                (field, score[field], unit, labels[field])
                for field, unit in (
                    ("temperature_mae_c", "°C"),
                    ("rain_correct_days", "day"),
                    ("rain_pairs", "day"),
                    ("rain_accuracy", "dimensionless"),
                )
                if score[field] is not None
                and (field == "temperature_mae_c" or score["rain_pairs"])
            ]
            for rain in score["rain_definitions"]:
                if not rain["paired_days"]:
                    continue
                for field, unit in (
                    ("correct_days", "day"),
                    ("paired_days", "day"),
                    ("era5_rain_days", "day"),
                    ("era5_rain_share", "dimensionless"),
                    ("majority_correct_days", "day"),
                    ("majority_accuracy", "dimensionless"),
                ):
                    entries.append(
                        (
                            f"{rain['definition']}:{field}",
                            rain[field],
                            unit,
                            f"{rain['event']} {field.replace('_', ' ')}; "
                            f"n={rain['paired_days']} paired days",
                        )
                    )
            for field, value, unit, label in entries:
                identifier = f"backtest:lead{score['lead_days']}:{field}"
                facts[identifier] = Fact(
                    id=identifier,
                    date=summary["end_date"],
                    value=value,
                    unit=unit,
                    latitude=summary["location"]["latitude"],
                    longitude=summary["location"]["longitude"],
                    source_url=summary["sources"][0]["request_url"],
                    supporting_urls=tuple(s["request_url"] for s in summary["sources"][1:]),
                    fetched_at=summary["computed_at"],
                    window_start=summary["start_date"],
                    window_end=summary["end_date"],
                    label=f"GFS model {score['lead_hours']}h comparison: {label}",
                )
        return facts
    evidence = result.get("evidence", {})
    if name not in {"get_forecast", "get_flood_signal"} or evidence.get("is_stale", True):
        return {}
    daily = evidence.get("daily", {})
    location = evidence.get("location", {})
    facts = {}
    for field, values in daily.get("values", {}).items():
        for day, value in zip(daily.get("time", []), values, strict=True):
            if value is None:
                continue
            identifier = f"{name}:{day[:10]}:{field}"
            facts[identifier] = Fact(
                id=identifier,
                date=day[:10],
                latitude=location["latitude"],
                longitude=location["longitude"],
                value=value,
                unit=daily["units"][field],
                source_url=evidence["request_url"],
                fetched_at=evidence["fetched_at"],
            )
    return facts


class AgentService:
    def __init__(
        self, provider: Provider, sources: SourceServices, catalogue: Catalogue, traces: TraceStore
    ) -> None:
        self.provider, self.sources, self.catalogue, self.traces = (
            provider,
            sources,
            catalogue,
            traces,
        )
        self.cache: OrderedDict[str, tuple[Claim, ...]] = OrderedDict()
        self.lock = asyncio.Lock()

    async def explain_plan(self, plan: Plan, language: Language) -> tuple[Plan, Answer]:
        async with self.lock:
            return await self._explain_plan(plan, language)

    async def _explain_plan(self, plan: Plan, language: Language) -> tuple[Plan, Answer]:
        trace_id = str(uuid4())
        facts = plan_facts(plan)
        identity = json.dumps(
            {
                "plot": plan.location.model_dump(),
                "crop": plan.crop,
                "language": language,
                "allowed_words": vocabulary(language),
                "sowing_date": str(plan.sowing_date),
                "day": datetime.now(UTC).date().isoformat(),
                "rules": plan.rule_version,
                "context": plan.agronomy_context.model_dump(mode="json"),
                "actions": [(a.date.isoformat(), a.kind, a.reason) for a in plan.actions],
                "facts": [fact.model_dump(exclude={"fetched_at"}) for fact in facts.values()],
            },
            sort_keys=True,
        )
        key = hashlib.sha256(identity.encode()).hexdigest()
        trace: dict[str, Any] = {
            "kind": "plan",
            "tools": [],
            "guardrail": "not_run",
            "cache_hit": False,
        }
        claims: tuple[Claim, ...] = ()
        note = "Agent explanations unavailable; deterministic evidence remains available."
        try:
            if not facts:
                raise ProviderError("required_evidence_unavailable")
            if key in self.cache:
                claims = self.cache[key]
                trace["cache_hit"] = True
            else:
                prompt = {
                    "task": (
                        "Explain all dated actions in one response. "
                        "One cited sentence per day. No tools or numbers in prose."
                    ),
                    "language": language,
                    "allowed_words": vocabulary(language),
                    "actions": [
                        {"date": a.date.isoformat(), "kind": a.kind, "reason": a.reason}
                        for a in plan.actions
                    ],
                    "facts": prompt_facts(facts),
                }
                claims = await self._draft(prompt, facts, trace)
                self.cache[key] = claims
                while len(self.cache) > 128:
                    self.cache.popitem(last=False)
            result = verify(claims, facts, language)
            if (
                not result.passed
                or not claims
                or {c.date for c in claims} != {a.date.isoformat() for a in plan.actions}
                or len(claims) != len(plan.actions)
            ):
                raise ProviderError("guardrail_rejected")
            by_day = {claim.date: claim for claim in claims}
            for action in plan.actions:
                if action.date.isoformat() in by_day:
                    action.explanation = by_day[action.date.isoformat()].text
                    action.explanation_status = "verified"
                    action.explanation_sources = (by_day[action.date.isoformat()].evidence_id,)
            trace["guardrail"] = "passed"
            note = "Explanations checked against this plan's cited numeric evidence."
        except (ProviderError, ValidationError) as exc:
            trace["error"] = exc.code if isinstance(exc, ProviderError) else "invalid_draft"
            claims = ()
        await self.traces.save(trace_id, trace)
        plan.agent_note = note
        plan.trace_id = trace_id
        return plan, Answer(
            trace_id=trace_id,
            language=language,
            status="verified" if claims else "unavailable",
            claims=claims,
            facts=tuple(facts.values()),
            note=note,
            formatted_facts={
                key: measurement(fact.value, fact.unit, language) for key, fact in facts.items()
            },
        )

    async def _draft(
        self, prompt: dict[str, Any], facts: dict[str, Fact], trace: dict[str, Any]
    ) -> tuple[Claim, ...]:
        language: Language = prompt["language"]
        contents = [{"role": "user", "parts": [{"text": json.dumps(prompt, ensure_ascii=False)}]}]
        for attempt in range(2):
            raw = await self.provider.generate(contents, Draft.model_json_schema())
            try:
                draft = Draft.model_validate(raw)
            except ValidationError:
                trace["guardrail"] = "invalid_draft"
                if attempt:
                    raise ProviderError("invalid_draft") from None
                contents.append({"role": "user", "parts": [{"text": "Correct the JSON schema."}]})
                continue
            result = verify(draft.claims, facts, language)
            trace["guardrail"] = result.model_dump()
            if (
                draft.claims
                and not draft.tools
                and result.passed
                and {c.date for c in draft.claims} == {a["date"] for a in prompt["actions"]}
                and len(draft.claims) == len(prompt["actions"])
            ):
                return draft.claims
            if attempt == 0:
                contents.append(
                    {
                        "role": "user",
                        "parts": [
                            {
                                "text": json.dumps(
                                    {
                                        "correction": result.discrepancies
                                        or ("Return cited explanatory claims, no tools.",),
                                    }
                                )
                            }
                        ],
                    }
                )
        raise ProviderError("guardrail_rejected")

    async def ask(self, question: str, context: PlotContext, language: Language) -> Answer:
        trace_id = str(uuid4())
        runner = ToolRunner(self.sources, self.catalogue, context)
        trace: dict[str, Any] = {"kind": "chat", "guardrail": "not_run"}
        facts: dict[str, Fact] = {}
        claims: tuple[Claim, ...] = ()
        await runner.execute(ToolCall(name="get_forecast"))
        await runner.execute(ToolCall(name="run_risk_assessment"))
        if runner.plan is not None:
            facts = plan_facts(runner.plan)
        contents = [
            {
                "role": "user",
                "parts": [
                    {
                        "text": json.dumps(
                            {
                                "question": question,
                                "language": language,
                                "allowed_words": vocabulary(language),
                                "context": context.model_dump(mode="json"),
                                "facts": prompt_facts(facts),
                                "actions": [a.reason for a in runner.plan.actions]
                                if runner.plan
                                else [],
                                "tools": {
                                    "get_forecast": "No arguments. Forecast for this plot.",
                                    "run_risk_assessment": "No arguments. Plot risk rules.",
                                    "get_soil": "No arguments. Optional modelled soil evidence.",
                                    "get_flood_signal": "No arguments. River discharge.",
                                    "get_backtest": "No arguments. GFS vs ERA5 metrics.",
                                    "get_mandi_prices": "Requires district and commodity strings.",
                                },
                            },
                            ensure_ascii=False,
                        )
                    }
                ],
            }
        ]
        note = "Agent unavailable. No agronomy answer was supplied from model memory."
        try:
            if not facts:
                raise ProviderError("required_evidence_unavailable")
            async with asyncio.timeout(100):
                for _ in range(4):
                    raw = await self.provider.generate(contents, Draft.model_json_schema())
                    try:
                        draft = Draft.model_validate(raw)
                    except ValidationError:
                        if trace.get("regenerated"):
                            raise ProviderError("invalid_draft") from None
                        trace["regenerated"] = True
                        contents.append(
                            {
                                "role": "user",
                                "parts": [{"text": "Correct the JSON schema and arguments."}],
                            }
                        )
                        continue
                    if draft.tools:
                        if len(runner.events) + len(draft.tools) > 8:
                            raise ProviderError("tool_budget_exhausted")
                        results = []
                        for call in draft.tools:
                            tool_result = await runner.execute(call)
                            added = tool_facts(call.name, tool_result)
                            if call.name == "run_risk_assessment" and runner.plan:
                                added.update(plan_facts(runner.plan))
                            facts.update(added)
                            results.append(
                                {
                                    "name": call.name,
                                    "result": tool_result,
                                    "citable_facts": prompt_facts(added),
                                }
                            )
                        contents.append(
                            {
                                "role": "user",
                                "parts": [
                                    {
                                        "text": json.dumps(
                                            {
                                                "tool_results": results,
                                                "instruction": (
                                                    "Acknowledge missing evidence. "
                                                    "Never invent replacement evidence."
                                                ),
                                            },
                                            ensure_ascii=False,
                                        )
                                    }
                                ],
                            }
                        )
                        continue
                    result = verify(draft.claims, facts, language)
                    trace["guardrail"] = result.model_dump()
                    if result.passed and draft.claims:
                        claims = draft.claims
                        note = "Numeric claims checked against cited evidence for this run."
                        break
                    if trace.get("regenerated"):
                        raise ProviderError("guardrail_rejected")
                    trace["regenerated"] = True
                    contents.append(
                        {
                            "role": "user",
                            "parts": [
                                {
                                    "text": json.dumps(
                                        {
                                            "discrepancies": result.discrepancies
                                            or ("Cited claims required",),
                                            "instruction": "Regenerate using cited evidence.",
                                        }
                                    )
                                }
                            ],
                        }
                    )
                else:
                    raise ProviderError("iteration_budget_exhausted")
        except (ProviderError, ValidationError, TimeoutError) as exc:
            trace["error"] = exc.code if isinstance(exc, ProviderError) else type(exc).__name__
        trace["tools"] = runner.events
        await self.traces.save(trace_id, trace)
        return Answer(
            trace_id=trace_id,
            language=language,
            status="verified" if claims else "unavailable",
            claims=claims,
            facts=tuple(facts.values()),
            note=note,
            plan=runner.plan,
            formatted_facts={
                key: measurement(fact.value, fact.unit, language) for key, fact in facts.items()
            },
        )
