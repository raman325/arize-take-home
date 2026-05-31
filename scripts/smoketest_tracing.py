"""Sanity check: register the exporter, emit a tiny LLM call, and one manual
span of each kind. Run before the rest of the pipeline so you can confirm
traces land in Arize AX before debugging anything more complicated.
"""

from __future__ import annotations

import sys
import time

sys.path.insert(0, ".")

from openinference.semconv.trace import OpenInferenceSpanKindValues  # noqa: E402

from weekend_planner.config import load_settings  # noqa: E402
from weekend_planner.llm_client import get_client  # noqa: E402
from weekend_planner.tracing import (  # noqa: E402
    set_output,
    set_retrieval_documents,
    set_tool,
    setup_tracing,
    span,
)


def main() -> None:
    setup_tracing()
    s = load_settings()

    with span("smoketest_root", OpenInferenceSpanKindValues.CHAIN, input_value={"hi": True}) as root:
        # 1. Auto-instrumented LLM call (should appear as a child LLM span)
        r = get_client().chat.completions.create(
            model=s.pipeline_model,
            messages=[{"role": "user", "content": "Reply with just: OK"}],
        )
        print("LLM said:", r.choices[0].message.content)

        # 2. Manual TOOL span
        with span("fake_tool", OpenInferenceSpanKindValues.TOOL) as t:
            set_tool(t, name="fake", parameters={"x": 1})
            set_output(t, {"result": "ok"})

        # 3. Manual RETRIEVER span with two fake documents
        with span("fake_retriever", OpenInferenceSpanKindValues.RETRIEVER, input_value="hello") as r2:
            set_retrieval_documents(
                r2,
                [
                    {"id": "a", "content": "alpha", "score": 0.9, "metadata": {"tag": "x"}},
                    {"id": "b", "content": "beta", "score": 0.4, "metadata": {"tag": "y"}},
                ],
            )

        set_output(root, {"status": "done"})

    # Give the batch exporter time to flush before the process exits.
    # (The default BatchSpanProcessor flushes on shutdown, but small CLI runs
    # often exit before the timer fires.)
    time.sleep(2)
    print("Smoketest complete. Check the 'weekend-planner' project in Arize AX.")


if __name__ == "__main__":
    main()
