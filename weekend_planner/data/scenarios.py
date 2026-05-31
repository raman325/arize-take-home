"""Test scenarios — each pins inputs so runs are reproducible.

Three scenarios were chosen to exercise distinct failure modes:
- sunny_baseline: happy path
- rainy_weekend: forces indoor-only plans (weather filter)
- saturday_morning_conflict: existing event collides with the morning slot
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Scenario:
    id: str
    family_request: str  # natural-language request; constraint-extraction LLM parses it


SCENARIOS: list[Scenario] = [
    Scenario(
        id="sunny_baseline",
        family_request=(
            "Two adults and our 2-year-old daughter. We want a fun weekend in DC. "
            "She naps from about 1 to 3pm both days, max 2 hours. "
            "Mornings are best for high-energy stuff. We'd prefer not to spend more "
            "than 30 minutes one-way driving anywhere."
        ),
    ),
    Scenario(
        id="rainy_weekend",
        family_request=(
            "Two adults and our 2-year-old. Rain is in the forecast both days. "
            "She naps 1–3 in the afternoon. We'd love a plan that keeps her "
            "engaged indoors but isn't just one museum after another."
        ),
    ),
    Scenario(
        id="saturday_morning_conflict",
        family_request=(
            "Two adults and our 2-year-old. We have a brunch we can't move at "
            "9:30–11:30 on Saturday. Sunday is open. Nap is 2–4 on Saturday, "
            "1–3 on Sunday. Please plan around the brunch."
        ),
    ),
]


SCENARIOS_BY_ID: dict[str, Scenario] = {s.id: s for s in SCENARIOS}
