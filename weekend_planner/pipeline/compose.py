"""Step 6 — Plan composition. AGENT span (with dynamic tool calling).

The composer is an agent, not a single LLM call: it can decide to call a
`lookup_more_activities(query)` tool to pull additional candidates from the
catalog if the initial ranked list doesn't cover what it needs. The outer
span is OpenInference kind AGENT to signal the autonomy boundary; each
inner chat.completions call is auto-instrumented (LLM span), and each
tool call surfaces as its own RETRIEVER span (via the underlying
`retrieve_activities` call).

The agent loop has a hard iteration cap so a runaway model can't burn the
budget. In practice the composer usually finishes in 1–2 turns.
"""

from __future__ import annotations

import json
from typing import Any

from openinference.semconv.trace import OpenInferenceSpanKindValues

from ..config import load_settings
from ..llm_client import get_client
from ..schemas import (
    CalendarLookup,
    Constraints,
    PlanSlot,
    RankedCandidate,
    WeatherForecast,
    WeekendPlan,
)
from ..tracing import set_output, span
from .retrieve import retrieve_activities

_MAX_AGENT_TURNS = 4

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "lookup_more_activities",
            "description": (
                "Search the DC family-activity catalog with a new query and "
                "return up to top_k additional candidates. Use this if the "
                "initial candidates miss something you need (e.g. you want "
                "more indoor backup options, or activities for a specific "
                "weather, or anything else not represented above)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural-language search query.",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "How many to return. Default 5.",
                    },
                },
                "required": ["query"],
            },
        },
    },
]


_SYSTEM = """\
You are an agent that plans a weekend for a DC family of two adults and a \
2-year-old. You have a tool, lookup_more_activities, to search the catalog \
for additional candidates if needed. Use the tool sparingly — only when \
the initial candidate list clearly misses something the plan needs.

When you have your final plan, respond with ONLY a JSON object matching \
the schema below (no preface, no tool calls):
{
  "saturday": [
    {"day": "Saturday", "start": "HH:MM", "end": "HH:MM",
     "activity_id": "<id>", "activity_name": "<name>", "notes": "<short>"}
  ],
  "sunday": [ ... ],
  "summary": "one paragraph"
}

Rules:
- Use only activities you've seen in the candidate list (initial or retrieved via the tool).
- 1-3 slots per day. Morning = most demanding activity.
- DO NOT overlap calendar events or nap windows (both provided below).
- DO NOT schedule outdoor activities on a day whose weather is not outdoor-friendly.
- Leave gaps for travel between slots.
"""


def _format_calendar(c: CalendarLookup) -> str:
    if not c.events:
        return "(none)"
    return "\n".join(
        f"- {e.day} {e.start.strftime('%H:%M')}-{e.end.strftime('%H:%M')}: {e.title}"
        for e in c.events
    )


def _format_nap(n) -> str:
    if n is None:
        return "(none)"
    return f"{n.start.strftime('%H:%M')}-{n.end.strftime('%H:%M')}"


def _format_weather(w: WeatherForecast) -> str:
    def line(d):
        return (
            f"- {d.day}: {d.condition}, high {d.high_f}°F, "
            f"precip {d.precip_chance}%, outdoor_friendly={d.outdoor_friendly}"
        )
    return "\n".join([line(w.saturday), line(w.sunday)])


def _format_candidates(ranked: list[RankedCandidate]) -> str:
    return "\n".join(
        f"- id={r.activity.id} | {r.activity.name} | "
        f"indoor={r.activity.indoor} | "
        f"ages {r.activity.min_age_years}-{r.activity.max_age_years} | "
        f"~{r.activity.typical_duration_min}min | "
        f"travel {r.activity.travel_minutes_from_home}min one-way | "
        f"tags={','.join(r.activity.tags)}"
        for r in ranked
    )


def _format_tool_result(activities: list) -> str:
    if not activities:
        return "[]"
    return json.dumps(
        [
            {
                "id": a["id"],
                "name": a["name"],
                "indoor": a["indoor"],
                "ages": f"{a['min_age']}-{a['max_age']}",
                "duration_min": a["duration_min"],
                "travel_min": a["travel_min"],
                "tags": a["tags"],
            }
            for a in activities
        ],
        indent=2,
    )


def _normalize_time(value: str) -> str:
    """Coerce '9:00' / '9:00:00' / '09:00' all to 'HH:MM:SS' that PlanSlot accepts."""
    parts = value.split(":")
    h = int(parts[0])
    m = int(parts[1]) if len(parts) > 1 else 0
    s = int(parts[2]) if len(parts) > 2 else 0
    return f"{h:02d}:{m:02d}:{s:02d}"


def _normalize_slot(slot: dict) -> dict:
    slot = dict(slot)
    if "start" in slot:
        slot["start"] = _normalize_time(str(slot["start"]))
    if "end" in slot:
        slot["end"] = _normalize_time(str(slot["end"]))
    return slot


def _parse_slots(raw_slots: list[dict]) -> list[PlanSlot]:
    """Build PlanSlots tolerantly. Skip malformed entries rather than crash —
    LLM JSON output is occasionally missing fields. A skipped slot becomes
    visible as a 'shorter day' in the plan rather than a hard pipeline
    failure, which is more demo-friendly and matches real-world agent code.
    """
    out: list[PlanSlot] = []
    for slot in raw_slots:
        try:
            out.append(PlanSlot(**_normalize_slot(slot)))
        except Exception:  # pydantic ValidationError or KeyError
            continue
    return out


def _run_tool(name: str, arguments: dict) -> list[dict]:
    """Execute a tool call. Today there's only one — easy to extend."""
    if name != "lookup_more_activities":
        return []
    query = arguments.get("query", "")
    top_k = int(arguments.get("top_k", 5))
    results = retrieve_activities(query, top_k=top_k)
    return [
        {
            "id": r.activity.id,
            "name": r.activity.name,
            "description": r.activity.description,
            "indoor": r.activity.indoor,
            "min_age": r.activity.min_age_years,
            "max_age": r.activity.max_age_years,
            "duration_min": r.activity.typical_duration_min,
            "travel_min": r.activity.travel_minutes_from_home,
            "tags": r.activity.tags,
            "similarity": r.similarity_score,
        }
        for r in results
    ]


def compose_plan(
    *,
    constraints: Constraints,
    weather: WeatherForecast,
    calendar: CalendarLookup,
    ranked: list[RankedCandidate],
) -> WeekendPlan:
    s = load_settings()
    client = get_client()
    initial_prompt = f"""\
Calendar events (do not overlap):
{_format_calendar(calendar)}

Nap windows (do not overlap):
- Saturday: {_format_nap(constraints.nap_window_saturday)}
- Sunday: {_format_nap(constraints.nap_window_sunday)}

Weather:
{_format_weather(weather)}

Initial candidates (ranked best-first):
{_format_candidates(ranked)}

Build the plan now. Call the tool only if you genuinely need more options."""

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": initial_prompt},
    ]

    with span(
        "compose_plan",
        OpenInferenceSpanKindValues.AGENT,
        input_value={
            "n_initial_candidates": len(ranked),
            "n_calendar_events": len(calendar.events),
        },
    ) as outer:
        tool_call_count = 0
        for turn in range(_MAX_AGENT_TURNS):
            resp = client.chat.completions.create(
                model=s.pipeline_model,
                messages=messages,
                tools=_TOOLS,
                # response_format coexists with tools on this proxy: when the
                # model wants to call a tool it ignores the format constraint
                # and emits tool_calls; when it produces a final answer the
                # content is guaranteed-valid JSON. Materially improves
                # final-plan reliability vs prompting alone.
                response_format={"type": "json_object"},
            )
            choice = resp.choices[0]
            if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
                # Record the assistant's tool-call message verbatim.
                messages.append(
                    {
                        "role": "assistant",
                        "content": choice.message.content or "",
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                },
                            }
                            for tc in choice.message.tool_calls
                        ],
                    }
                )
                # Execute each tool call. Each retrieve emits its own RETRIEVER span.
                for tc in choice.message.tool_calls:
                    tool_call_count += 1
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    result = _run_tool(tc.function.name, args)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "name": tc.function.name,
                            "content": _format_tool_result(result),
                        }
                    )
                continue

            # No tool calls → expect final JSON plan.
            raw = choice.message.content or "{}"
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                # Some models wrap JSON in ```json fences. Strip and retry.
                stripped = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
                data = json.loads(stripped)
            plan = WeekendPlan(
                saturday=_parse_slots(data.get("saturday", [])),
                sunday=_parse_slots(data.get("sunday", [])),
                summary=data.get("summary", ""),
            )
            set_output(
                outer,
                {
                    "turns_taken": turn + 1,
                    "tool_calls": tool_call_count,
                    "plan": plan.model_dump(mode="json"),
                },
            )
            return plan

        raise RuntimeError(
            f"agent exceeded {_MAX_AGENT_TURNS} turns without producing a final plan"
        )
