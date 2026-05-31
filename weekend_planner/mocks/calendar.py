"""Mock calendar service — canned per-scenario events."""

from __future__ import annotations

from datetime import time

from ..schemas import CalendarEvent, CalendarLookup

_EVENTS: dict[str, list[CalendarEvent]] = {
    "sunny_baseline": [],
    "rainy_weekend": [],
    "saturday_morning_conflict": [
        CalendarEvent(
            day="Saturday",
            start=time(9, 30),
            end=time(11, 30),
            title="Brunch with friends",
        ),
    ],
}


def get_calendar(scenario_id: str) -> CalendarLookup:
    if scenario_id not in _EVENTS:
        raise KeyError(f"No mock calendar for scenario {scenario_id!r}")
    return CalendarLookup(events=list(_EVENTS[scenario_id]))
