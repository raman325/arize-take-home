"""Run one scenario end-to-end and print the resulting plan.

Usage:
    uv run python scripts/run_app.py [scenario_id]

Default scenario_id is sunny_baseline. Traces flow to the Arize AX project
configured in .env (ARIZE_PROJECT_NAME, defaults to 'weekend-planner').
"""

from __future__ import annotations

import json
import sys
import time

sys.path.insert(0, ".")

from weekend_planner.data.scenarios import SCENARIOS_BY_ID  # noqa: E402
from weekend_planner.pipeline.plan import run_pipeline  # noqa: E402
from weekend_planner.tracing import setup_tracing  # noqa: E402


def main() -> None:
    setup_tracing()
    scenario_id = sys.argv[1] if len(sys.argv) > 1 else "sunny_baseline"
    if scenario_id not in SCENARIOS_BY_ID:
        sys.exit(
            f"unknown scenario {scenario_id!r}; "
            f"available: {list(SCENARIOS_BY_ID)}"
        )

    print(f"\n=== Running scenario: {scenario_id} ===\n")
    run = run_pipeline(scenario_id)

    print("Constraints:")
    print(json.dumps(run.constraints.model_dump(mode="json"), indent=2))
    print(f"\nRetrieved {len(run.retrieved)} activities, kept {len(run.ranked)} after rank.")
    print("\nPlan:")
    print(json.dumps(run.plan.model_dump(mode="json"), indent=2))

    # Allow the BatchSpanProcessor to flush before process exit.
    time.sleep(2)


if __name__ == "__main__":
    main()
