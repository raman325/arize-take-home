"""Step 3 — Calendar lookup. TOOL span."""

from __future__ import annotations

from openinference.semconv.trace import OpenInferenceSpanKindValues

from ..mocks.calendar import get_calendar
from ..schemas import CalendarLookup
from ..tracing import set_output, set_tool, span


def lookup_calendar(scenario_id: str) -> CalendarLookup:
    with span("calendar_lookup", OpenInferenceSpanKindValues.TOOL) as s:
        set_tool(s, name="calendar_events", parameters={"scenario_id": scenario_id})
        result = get_calendar(scenario_id)
        set_output(s, result.model_dump(mode="json"))
        return result
