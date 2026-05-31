"""Production workflow: run the pipeline 3 times with varied inputs to seed
Arize AX with real-shape OpenInference traces (no experiment wrapping,
no eval upload — just live spans).

The 3 runs hit different scenarios so the AX trace list shows variety
(different retrieval queries, different ranked candidates, different
plans). Each run is its own root CHAIN span with the 6 children below it.
"""

from __future__ import annotations

import sys
import time

sys.path.insert(0, ".")

from weekend_planner.data.scenarios import SCENARIOS  # noqa: E402
from weekend_planner.pipeline.plan import run_pipeline  # noqa: E402
from weekend_planner.tracing import setup_tracing  # noqa: E402


def main() -> None:
    setup_tracing()
    for i, scenario in enumerate(SCENARIOS, 1):
        print(f"\n--- prod run {i}/{len(SCENARIOS)}: {scenario.id} ---")
        run = run_pipeline(scenario.id)
        print(
            f"  → {len(run.plan.saturday)}+{len(run.plan.sunday)} slots, "
            f"summary: {run.plan.summary[:80]}…"
        )
        # Small wall-clock gap so the AX timeline view shows the runs
        # as distinct points in time instead of one blob.
        if i < len(SCENARIOS):
            time.sleep(3)
    # Let the batch processor flush.
    time.sleep(3)
    print(
        "\nProd seed complete. Check the 'weekend-planner' project's Traces tab "
        "in Arize AX for 3 fresh root CHAIN spans, each with 6 children."
    )


if __name__ == "__main__":
    main()
