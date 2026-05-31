"""Dev workflow: upload scenarios as an Arize Dataset, run the pipeline as
an Experiment, attach evaluators. Eval results land linked to the run.

Usage:
    uv run python scripts/run_evals.py [--dataset-name NAME] [--experiment-name NAME]

The first run creates the dataset; subsequent runs replace its examples
(simple semantics — we're not exercising dataset versioning here).
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from typing import Mapping

sys.path.insert(0, ".")

from arize.client import ArizeClient  # noqa: E402

from evals.judges import PacingArcEval, RetrievalPrecisionEval  # noqa: E402
from evals.programmatic import (  # noqa: E402
    NoCalendarConflictsEval,
    RespectsNapWindowEval,
)
from weekend_planner.config import load_settings  # noqa: E402
from weekend_planner.data.scenarios import SCENARIOS  # noqa: E402
from weekend_planner.pipeline.plan import _retrieval_query, run_pipeline  # noqa: E402
from weekend_planner.tracing import setup_tracing  # noqa: E402

_DEFAULT_DATASET = "weekend-planner-scenarios"


def _dataset_examples() -> list[Mapping]:
    """One dict per scenario, FLAT.

    PM note: nested dicts in dataset rows get serialized to JSON strings by
    the SDK. So we use flat rows + bind the task to `dataset_row` instead
    of `input`. Both conventions are valid; flat-row is the one that
    survives the upload round-trip intact.
    """
    return [
        {"scenario_id": s.id, "family_request": s.family_request}
        for s in SCENARIOS
    ]


def _ensure_dataset(client: ArizeClient, space_id: str, name: str):
    """Create the dataset if missing; otherwise reuse it.

    PM note: AX exposes append + version semantics, but for this demo we
    just create-once-and-reuse so the experiment list stays uncluttered.
    """
    existing = client.datasets.list(name=name, space=space_id, limit=10)
    matches = [d for d in existing.datasets if d.name == name]
    if matches:
        print(f"[dataset] reusing existing: {name} (id={matches[0].id})")
        return matches[0]
    print(f"[dataset] creating: {name}")
    return client.datasets.create(
        name=name, space=space_id, examples=_dataset_examples()
    )


def _task(dataset_row: dict) -> dict:
    """The experiment task — invoked once per dataset row by AX.

    Param name MUST be one of {input, output, metadata, dataset_row}; the
    SDK binds based on the name (see arize.experiments.functions
    ._bind_task_signature). `dataset_row` gives us the full uploaded row.
    """
    scenario_id = dataset_row["scenario_id"]
    run = run_pipeline(scenario_id)
    return {
        "plan": run.plan.model_dump(mode="json"),
        "constraints": run.constraints.model_dump(mode="json"),
        "calendar_events": [e.model_dump(mode="json") for e in run.calendar.events],
        "weather": run.weather.model_dump(mode="json"),
        "retrieval_query": _retrieval_query(run.constraints),
        "retrieved": [
            {
                "id": r.activity.id,
                "name": r.activity.name,
                "description": r.activity.description,
                "indoor": r.activity.indoor,
                "min_age": r.activity.min_age_years,
                "max_age": r.activity.max_age_years,
                "similarity": r.similarity_score,
            }
            for r in run.retrieved
        ],
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dataset-name", default=_DEFAULT_DATASET)
    p.add_argument(
        "--experiment-name",
        default=f"weekend-planner-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
    )
    args = p.parse_args()

    setup_tracing()
    s = load_settings()
    client = ArizeClient(api_key=s.arize_api_key)

    dataset = _ensure_dataset(client, s.arize_space_id, args.dataset_name)
    print(f"[experiment] running: {args.experiment_name}")
    experiment, df = client.experiments.run(
        name=args.experiment_name,
        dataset=args.dataset_name,
        space=s.arize_space_id,
        task=_task,
        evaluators=[
            NoCalendarConflictsEval(),
            RespectsNapWindowEval(),
            PacingArcEval(),
            RetrievalPrecisionEval(),
        ],
        concurrency=1,  # keep traces readable, not racing
        exit_on_error=False,
    )

    print("\n=== Experiment summary ===")
    print(f"Dataset:    {dataset.name}")
    print(f"Experiment: {getattr(experiment, 'name', args.experiment_name)}")
    print(f"Rows:       {len(df)}")
    print(f"Columns:    {list(df.columns)}")
    print()
    # Show eval-* columns (label/score) side-by-side with the row id.
    eval_cols = [
        c for c in df.columns
        if any(
            c.endswith(suf) for suf in (".score", ".label", "_score", "_label")
        )
    ]
    show_cols = [c for c in df.columns if "id" in c.lower()][:1] + eval_cols
    if show_cols:
        print(df[show_cols].to_string(index=False))
    else:
        print(df.to_string(index=False))


if __name__ == "__main__":
    main()
