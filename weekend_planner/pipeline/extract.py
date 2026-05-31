"""Step 1 — Constraint extraction. LLM span (manual wrapper).

The OpenAIInstrumentor automatically emits a child LLM span for the
chat.completions call below — but we wrap the whole step in our own outer
LLM span so the trace shows a single "extract_constraints" unit instead of a
bare provider call. Input + output get the OpenInference attributes; token
counts come from the inner auto-span.
"""

from __future__ import annotations

import json
from datetime import time

from openinference.semconv.trace import OpenInferenceSpanKindValues

from ..config import load_settings
from ..llm_client import get_client
from ..schemas import Constraints, NapWindow
from ..tracing import set_output, span

_EXTRACTION_PROMPT = """\
You extract scheduling constraints from a family's weekend-planning request.

Return ONLY a JSON object with this shape (omit keys you can't infer):
{{
  "child_age_years": <number>,
  "nap_window_saturday": {{"start": "HH:MM", "end": "HH:MM"}},
  "nap_window_sunday": {{"start": "HH:MM", "end": "HH:MM"}},
  "preferences": ["short preference strings"],
  "notes": "anything else relevant"
}}

Times must be 24-hour HH:MM strings. Nap windows are when the child is
unavailable. If the request gives a range like "1 to 3 or 2 to 4", pick the
earlier window (1-3) unless explicitly told otherwise.

Family request:
{request}
"""


def _parse_time(value: str) -> time:
    h, m = value.split(":")
    return time(int(h), int(m))


def _to_nap(d: dict | None) -> NapWindow | None:
    if not d:
        return None
    return NapWindow(start=_parse_time(d["start"]), end=_parse_time(d["end"]))


def extract_constraints(family_request: str) -> Constraints:
    s = load_settings()
    with span(
        "extract_constraints",
        OpenInferenceSpanKindValues.LLM,
        input_value={"request": family_request},
    ) as outer:
        resp = get_client().chat.completions.create(
            model=s.pipeline_model,
            messages=[
                {"role": "system", "content": "Extract scheduling constraints. Respond with JSON only."},
                {"role": "user", "content": _EXTRACTION_PROMPT.format(request=family_request)},
            ],
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)
        constraints = Constraints(
            child_age_years=float(data.get("child_age_years", 0)),
            nap_window_saturday=_to_nap(data.get("nap_window_saturday")),
            nap_window_sunday=_to_nap(data.get("nap_window_sunday")),
            preferences=list(data.get("preferences", [])),
            notes=data.get("notes", ""),
        )
        set_output(outer, constraints.model_dump(mode="json"))
        return constraints
