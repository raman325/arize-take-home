"""Step 5 — Rank and filter. CHAIN span.

Pure code: applies the hard constraints (weather suitability, age range,
calendar conflicts at the day level, travel budget) and produces a
ranked-and-filtered list of candidates. Filter reasons are recorded so the
trace shows *why* something dropped — useful both for debugging and for the
PM's observability story.
"""

from __future__ import annotations

from openinference.semconv.trace import OpenInferenceSpanKindValues

from ..schemas import (
    Constraints,
    RankedCandidate,
    RetrievedActivity,
    WeatherForecast,
)
from ..tracing import set_output, span

_TRAVEL_BUDGET_MIN = 30  # soft preference from the family request


def rank_and_filter(
    candidates: list[RetrievedActivity],
    *,
    constraints: Constraints,
    weather: WeatherForecast,
) -> list[RankedCandidate]:
    """Rank candidates against weather + age + travel budget.

    Note: calendar conflicts are *time-of-day* concerns and only matter when
    the composer assigns a slot. They don't filter the candidate set, so the
    calendar isn't an input here — it's consumed in compose_plan.
    """
    with span("rank_and_filter", OpenInferenceSpanKindValues.CHAIN) as s:
        rainy_day = (not weather.saturday.outdoor_friendly) or (
            not weather.sunday.outdoor_friendly
        )
        # We treat the weekend's *worst* day as the constraint for outdoor filtering;
        # the composer can still place outdoor activities on the good day.
        both_days_indoor_only = (
            not weather.saturday.outdoor_friendly
            and not weather.sunday.outdoor_friendly
        )

        results: list[RankedCandidate] = []
        for c in candidates:
            reasons: list[str] = []
            suit = c.similarity_score  # start from semantic similarity

            # Hard filter: age range.
            if not (
                c.activity.min_age_years
                <= constraints.child_age_years
                <= c.activity.max_age_years
            ):
                reasons.append(
                    f"outside age range "
                    f"[{c.activity.min_age_years}, {c.activity.max_age_years}]"
                )
                # dropped — don't include
                continue

            # Hard filter: both days fully rained out → drop pure-outdoor options.
            if both_days_indoor_only and not c.activity.indoor:
                reasons.append("outdoor-only activity, both days rained out")
                continue

            # Soft penalty: travel budget. -0.1 per 10min over budget, floored at 0.
            over = max(0, c.activity.travel_minutes_from_home - _TRAVEL_BUDGET_MIN)
            travel_penalty = 0.1 * (over / 10)
            if travel_penalty > 0:
                reasons.append(
                    f"travel {c.activity.travel_minutes_from_home}min exceeds "
                    f"{_TRAVEL_BUDGET_MIN}min budget (-{travel_penalty:.2f})"
                )
                suit -= travel_penalty

            # Soft boost: indoor activities get a bump when weather is mixed.
            if rainy_day and c.activity.indoor:
                suit += 0.1
                reasons.append("indoor boost (mixed weather)")

            results.append(
                RankedCandidate(
                    activity=c.activity,
                    similarity_score=c.similarity_score,
                    suitability_score=max(0.0, suit),
                    filter_reasons=reasons,
                )
            )

        # Sort by suitability descending. Ties broken by similarity.
        results.sort(
            key=lambda r: (r.suitability_score, r.similarity_score), reverse=True
        )

        set_output(
            s,
            {
                "kept": len(results),
                "dropped": len(candidates) - len(results),
                "ranked": [
                    {
                        "id": r.activity.id,
                        "name": r.activity.name,
                        "score": round(r.suitability_score, 3),
                        "reasons": r.filter_reasons,
                    }
                    for r in results
                ],
            },
        )
        return results
