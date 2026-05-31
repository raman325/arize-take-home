"""Orchestrator — wires the 6 steps under one CHAIN span.

The outer CHAIN span makes the entire pipeline run a single root span in
Arize AX, so you can see "5 of 5 scenarios passed eval X" rather than
"30 unrelated LLM/TOOL/RETRIEVER spans".
"""

from __future__ import annotations

from dataclasses import dataclass

from openinference.semconv.trace import OpenInferenceSpanKindValues

from ..data.scenarios import SCENARIOS_BY_ID
from ..schemas import (
    CalendarLookup,
    Constraints,
    RankedCandidate,
    RetrievedActivity,
    WeatherForecast,
    WeekendPlan,
)
from ..tracing import set_output, span
from .calendar import lookup_calendar
from .compose import compose_plan
from .extract import extract_constraints
from .rank import rank_and_filter
from .retrieve import retrieve_activities
from .weather import lookup_weather


@dataclass
class PipelineRun:
    scenario_id: str
    family_request: str
    constraints: Constraints
    weather: WeatherForecast
    calendar: CalendarLookup
    retrieved: list[RetrievedActivity]
    ranked: list[RankedCandidate]
    plan: WeekendPlan


def _retrieval_query(constraints: Constraints) -> str:
    """Build a query string for the retriever from the extracted constraints."""
    prefs = ", ".join(constraints.preferences) if constraints.preferences else "family fun"
    return (
        f"weekend activities for a {constraints.child_age_years:.0f}-year-old "
        f"in DC; family preferences: {prefs}"
    )


def run_pipeline(scenario_id: str) -> PipelineRun:
    scenario = SCENARIOS_BY_ID[scenario_id]
    with span(
        "weekend_planner_pipeline",
        OpenInferenceSpanKindValues.CHAIN,
        input_value={"scenario_id": scenario_id, "request": scenario.family_request},
    ) as root:
        constraints = extract_constraints(scenario.family_request)
        weather = lookup_weather(scenario_id)
        calendar = lookup_calendar(scenario_id)
        retrieved = retrieve_activities(_retrieval_query(constraints))
        ranked = rank_and_filter(
            retrieved, constraints=constraints, weather=weather
        )
        plan = compose_plan(
            constraints=constraints, weather=weather, calendar=calendar, ranked=ranked
        )
        set_output(
            root,
            {
                "n_slots_saturday": len(plan.saturday),
                "n_slots_sunday": len(plan.sunday),
                "summary": plan.summary,
            },
        )
        return PipelineRun(
            scenario_id=scenario_id,
            family_request=scenario.family_request,
            constraints=constraints,
            weather=weather,
            calendar=calendar,
            retrieved=retrieved,
            ranked=ranked,
            plan=plan,
        )
