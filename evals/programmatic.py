"""Code evaluators — deterministic structural checks against the produced plan.

Each subclass is a thin adapter over a pure Python check. They get attached
to an Arize Experiment via `experiments.run(evaluators=[...])` and the
results land as columns next to each run in the AX UI.
"""

from __future__ import annotations

from datetime import time
from typing import Mapping

from arize.experiments.evaluators.base import (
    CodeEvaluator,
    EvaluationResult,
)


def _parse_time(s: str) -> time:
    """Parse 'HH:MM' or 'HH:MM:SS'."""
    parts = s.split(":")
    return time(int(parts[0]), int(parts[1]))


def _slots(plan: Mapping) -> list[dict]:
    return [*plan.get("saturday", []), *plan.get("sunday", [])]


class NoCalendarConflictsEval(CodeEvaluator):
    """Score 1.0 if no plan slot overlaps any existing calendar event, else 0."""

    _name = "no_calendar_conflicts"

    def evaluate(self, *, output=None, dataset_row=None, **_) -> EvaluationResult:
        plan = (output or {}).get("plan", {})
        events = (output or {}).get("calendar_events", [])
        violations: list[str] = []
        for slot in _slots(plan):
            s_start = _parse_time(slot["start"])
            s_end = _parse_time(slot["end"])
            for ev in events:
                if ev["day"] != slot["day"]:
                    continue
                e_start = _parse_time(ev["start"])
                e_end = _parse_time(ev["end"])
                if s_start < e_end and s_end > e_start:
                    violations.append(
                        f"{slot['activity_name']} ({slot['day']} "
                        f"{slot['start']}-{slot['end']}) overlaps "
                        f"'{ev['title']}' ({ev['start']}-{ev['end']})"
                    )
        passed = not violations
        return EvaluationResult(
            score=1.0 if passed else 0.0,
            label="pass" if passed else "fail",
            explanation="No conflicts." if passed else "; ".join(violations),
            metadata={"violations": len(violations)},
        )


class RespectsNapWindowEval(CodeEvaluator):
    """Score 1.0 if no slot overlaps the day's nap window, else 0."""

    _name = "respects_nap_window"

    def evaluate(self, *, output=None, dataset_row=None, **_) -> EvaluationResult:
        plan = (output or {}).get("plan", {})
        constraints = (output or {}).get("constraints", {})
        nap_sat = constraints.get("nap_window_saturday")
        nap_sun = constraints.get("nap_window_sunday")
        violations: list[str] = []
        for slot in _slots(plan):
            nap = nap_sat if slot["day"] == "Saturday" else nap_sun
            if not nap:
                continue
            s_start = _parse_time(slot["start"])
            s_end = _parse_time(slot["end"])
            n_start = _parse_time(nap["start"])
            n_end = _parse_time(nap["end"])
            if s_start < n_end and s_end > n_start:
                violations.append(
                    f"{slot['activity_name']} ({slot['day']} "
                    f"{slot['start']}-{slot['end']}) overlaps nap "
                    f"{nap['start']}-{nap['end']}"
                )
        passed = not violations
        return EvaluationResult(
            score=1.0 if passed else 0.0,
            label="pass" if passed else "fail",
            explanation="Nap respected." if passed else "; ".join(violations),
            metadata={"violations": len(violations)},
        )
