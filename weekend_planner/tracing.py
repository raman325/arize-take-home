"""Tracing setup: register Arize AX exporter + auto-instrument the OpenAI SDK.

Call `setup_tracing()` exactly once at app startup (before any other module
calls `get_client()`). After that:

- Every OpenAI SDK call auto-emits an LLM span (token counts, cost, latency).
- Use `span(name, kind, ...)` as a context manager to wrap each pipeline step
  with the correct OpenInference span.kind and input/output attributes.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Iterator

from arize.otel import register
from openinference.instrumentation.openai import OpenAIInstrumentor
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry import trace
from opentelemetry.trace import Span, Status, StatusCode

from .config import load_settings

_TRACER_NAME = "weekend_planner"
_initialized = False


def setup_tracing() -> None:
    """Idempotent: registers the Arize AX OTLP exporter and instruments OpenAI."""
    global _initialized
    if _initialized:
        return
    s = load_settings()
    register(
        space_id=s.arize_space_id,
        api_key=s.arize_api_key,
        project_name=s.arize_project_name,
    )
    OpenAIInstrumentor().instrument()
    _initialized = True


def _tracer():
    return trace.get_tracer(_TRACER_NAME)


def _coerce(value: Any) -> str:
    """JSON when possible, str() as fallback. Spans store strings/JSON best."""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


@contextmanager
def span(
    name: str,
    kind: OpenInferenceSpanKindValues,
    *,
    input_value: Any | None = None,
) -> Iterator[Span]:
    """Open a span tagged with an OpenInference span kind.

    Sets `openinference.span.kind` + optionally `input.value`. Use
    `set_output()` and the helpers below to attach output / retrieval docs
    / tool metadata before the context exits.
    """
    with _tracer().start_as_current_span(name) as s:
        s.set_attribute(SpanAttributes.OPENINFERENCE_SPAN_KIND, kind.value)
        if input_value is not None:
            s.set_attribute(SpanAttributes.INPUT_VALUE, _coerce(input_value))
            s.set_attribute(SpanAttributes.INPUT_MIME_TYPE, "application/json")
        try:
            yield s
        except Exception as exc:
            s.set_status(Status(StatusCode.ERROR, str(exc)))
            s.record_exception(exc)
            raise


def set_output(s: Span, value: Any) -> None:
    s.set_attribute(SpanAttributes.OUTPUT_VALUE, _coerce(value))
    s.set_attribute(SpanAttributes.OUTPUT_MIME_TYPE, "application/json")


def set_tool(s: Span, *, name: str, parameters: Any) -> None:
    s.set_attribute(SpanAttributes.TOOL_NAME, name)
    s.set_attribute(SpanAttributes.TOOL_PARAMETERS, _coerce(parameters))


def set_retrieval_documents(s: Span, docs: list[dict[str, Any]]) -> None:
    """Set OpenInference retrieval.documents.* per-document attributes.

    Each doc dict should have: id (str), content (str), score (float),
    metadata (dict). The flat attribute layout below is what Phoenix /
    Arize AX expect for retrieval-relevance evals to bind to documents.
    """
    for i, d in enumerate(docs):
        prefix = f"{SpanAttributes.RETRIEVAL_DOCUMENTS}.{i}.document"
        s.set_attribute(f"{prefix}.id", str(d.get("id", "")))
        s.set_attribute(f"{prefix}.content", str(d.get("content", "")))
        if "score" in d:
            s.set_attribute(f"{prefix}.score", float(d["score"]))
        if d.get("metadata"):
            s.set_attribute(f"{prefix}.metadata", _coerce(d["metadata"]))
