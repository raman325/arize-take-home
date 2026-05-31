# Family weekend planner — an agent application instrumented with Arize AX

A small AI **agent** that demonstrates **Arize AX** observability and evaluation. The agent plans a DC weekend for a family of three (two adults + a toddler) and respects scheduling conflicts, weather, the child's age, and the nap window.

It's agentic in the substantive sense: the final composer step is an **autonomous loop with tool calling** — it can decide to call `lookup_more_activities(query)` to pull additional candidates from the catalog if the initial retrieval doesn't cover what it needs. The wrapping span uses OpenInference kind `AGENT`; each tool call surfaces as its own `RETRIEVER` span via the underlying retriever.

This repo exercises **both AX workflows** that the take-home asks about:

| Workflow | Script | What it does in AX |
|---|---|---|
| **Production observability** | `scripts/seed_prod_traffic.py` | Runs the pipeline 3 times. 3 fresh root CHAIN spans land in the **Traces** tab, each with 6 children (LLM / TOOL / RETRIEVER / CHAIN spans) carrying OpenInference attributes. |
| **Development (dataset + experiment + evals)** | `scripts/run_evals.py` | Uploads scenarios as an Arize **Dataset**, runs the pipeline as an **Experiment**, and attaches 4 evaluators. Eval scores + labels + explanations land linked to the experiment runs. |

## Architecture — 6 traced steps

Each step is a single Python function in `weekend_planner/pipeline/`. Each emits one manually-wrapped OpenInference span with the correct `openinference.span.kind`. Inside the LLM-touching steps, the auto-instrumentor (`OpenAIInstrumentor`) emits a child span carrying token counts, latency, and cost.

```
weekend_planner_pipeline (CHAIN)
├── extract_constraints       (LLM)        ← family request → structured constraints
│   └── chat.completions      (LLM, auto-instrumented)
├── weather_lookup            (TOOL)       ← scenario_id → forecast
├── calendar_lookup           (TOOL)       ← scenario_id → events
├── activity_retrieval        (RETRIEVER)  ← query → top-k activities w/ scores
│   └── embeddings.create     (LLM, auto-instrumented)
├── rank_and_filter           (CHAIN)      ← filter by age/weather/travel, then rank
└── compose_plan              (AGENT)      ← autonomous tool-calling loop
    ├── chat.completions      (LLM, auto-instrumented)
    ├── (optional, when the agent calls the tool):
    │   activity_retrieval    (RETRIEVER)  ← dynamic re-query
    │     └── embeddings.create (LLM, auto-instrumented)
    └── chat.completions      (LLM, auto-instrumented) — final plan JSON
```

The `saturday_morning_conflict` scenario reliably triggers the tool call (the brunch constraint forces the agent to look for more around-the-conflict options). The other scenarios usually finish in one turn. This *variability* is the point — the trace shows whether the agent reached for the tool, and the AGENT span's `output.value` records `turns_taken` and `tool_calls` for inspection.

## Evaluators

Four evaluators run inside the Experiment in `run_evals.py`:

| Name | Kind | Checks |
|---|---|---|
| `no_calendar_conflicts` | code | No plan slot overlaps any existing calendar event |
| `respects_nap_window` | code | No slot overlaps the day's extracted nap window |
| `pacing_arc` | LLM-judge | Plan has high-energy mornings, restful post-nap, balanced Sat/Sun |
| `retrieval_precision` | LLM-judge | Fraction of retrieved activities the judge labels relevant to the query |

The LLM-judge evaluators are written by composing `phoenix.evals.create_classifier(...)` (Phoenix's rubric+choices+LLM helper) inside `arize.experiments.evaluators.base.LLMEvaluator` subclasses (the type `experiments.run(...)` expects). The two libraries layer cleanly — Phoenix handles prompt templating and parsing; the Arize base class handles transport.

## Setup

Requires `uv` and Python 3.12.

```bash
# 1. Fill in credentials
cp .env.example .env
# edit .env:
#   LITELLM_BASE_URL   (must end in /v1 — the OpenAI SDK does NOT auto-add it)
#   LITELLM_API_KEY
#   PIPELINE_MODEL     (e.g. gpt-4o-mini, or anything OpenAI-compatible)
#   JUDGE_MODEL        (same)
#   EMBEDDING_MODEL    (e.g. text-embedding-3-small)
#   ARIZE_SPACE_ID     (app.arize.com → Settings → API & Space Keys)
#   ARIZE_API_KEY
#   ARIZE_PROJECT_NAME (defaults to "weekend-planner")

# 2. Install deps
uv sync

# 3. (optional) sanity-check tracing — emits one of each span kind, no LLM work
uv run python scripts/smoketest_tracing.py
```

## Run

```bash
# Run one scenario, end-to-end. Traces flow to AX.
uv run python scripts/run_app.py sunny_baseline
uv run python scripts/run_app.py rainy_weekend
uv run python scripts/run_app.py saturday_morning_conflict

# Production workflow: 3 runs, no experiment wrapping.
uv run python scripts/seed_prod_traffic.py

# Development workflow: upload dataset + run experiment + 4 evaluators.
uv run python scripts/run_evals.py
```

The first retrieve-step call seeds the Chroma collection in `chroma_store/` (one embeddings round-trip per activity, ~15 calls). Subsequent runs reuse the persisted embeddings.

## Project structure

```
weekend_planner/
├── config.py             # .env loading
├── tracing.py            # arize.otel.register + OpenAIInstrumentor + span helper
├── llm_client.py         # one OpenAI SDK client pointed at the LiteLLM proxy
├── schemas.py            # pydantic models passed between steps
├── data/
│   ├── activities.py     # ~15 DC family activities (catalog seeded into Chroma)
│   └── scenarios.py      # 3 reproducible test scenarios
├── mocks/
│   ├── weather.py        # canned per-scenario forecasts
│   └── calendar.py       # canned per-scenario events
└── pipeline/
    ├── extract.py        # step 1 — LLM
    ├── weather.py        # step 2 — TOOL
    ├── calendar.py       # step 3 — TOOL
    ├── retrieve.py       # step 4 — RETRIEVER (Chroma + embeddings)
    ├── rank.py           # step 5 — CHAIN
    ├── compose.py        # step 6 — LLM
    └── plan.py           # orchestrator — wraps all 6 in a parent CHAIN span

evals/
├── programmatic.py       # NoCalendarConflictsEval, RespectsNapWindowEval (CodeEvaluator subclasses)
└── judges.py             # PacingArcEval, RetrievalPrecisionEval (LLMEvaluator subclasses, backed by phoenix.evals)

scripts/
├── smoketest_tracing.py  # sanity check — one of each span kind, no LLM work
├── run_app.py            # one scenario end-to-end
├── seed_prod_traffic.py  # prod workflow: 3 runs, no experiment
└── run_evals.py          # dev workflow: dataset + experiment + 4 evaluators
```

## Observability story — what to look for in Arize AX

After running both workflows, the `weekend-planner` project in AX has:

### In **Traces** (from `seed_prod_traffic.py` or `run_app.py`)
- **3+ root spans** named `weekend_planner_pipeline` (kind=CHAIN)
- Each expands to show 6 children: `extract_constraints` (LLM) → `weather_lookup` (TOOL) → `calendar_lookup` (TOOL) → `activity_retrieval` (RETRIEVER) → `rank_and_filter` (CHAIN) → `compose_plan` (**AGENT**)
- The AGENT span on `compose_plan` shows 1+ auto-instrumented `chat.completions` calls inside it; when the agent chooses to invoke its tool, an additional `activity_retrieval` RETRIEVER span appears as well
- Each LLM-step child has an inner auto-instrumented `chat.completions` / `embeddings.create` span with token counts and latency
- The retrieval span shows `retrieval.documents.{i}.document.{id,content,score,metadata}` — every retrieved activity inspectable inline
- The CHAIN span on `rank_and_filter` carries an `output.value` showing why each candidate was dropped or boosted
- The AGENT span's `output.value` records `turns_taken` and `tool_calls` — at-a-glance signal for how much autonomous work the agent did

### In **Datasets** (from `run_evals.py`)
- `weekend-planner-scenarios` with 3 rows (one per scenario)

### In **Experiments** (from `run_evals.py`)
- One experiment per `run_evals.py` invocation, named `weekend-planner-<timestamp>`
- 3 rows × 4 evaluator columns:
  - `eval.no_calendar_conflicts.{score,label,explanation}`
  - `eval.respects_nap_window.{score,label,explanation}`
  - `eval.pacing_arc.{score,label,explanation}`
  - `eval.retrieval_precision.{score,label,explanation,metadata.per_doc}`

### Demoable failure
With agentic compose, plan-level failures shift run-to-run because the agent's path isn't deterministic. In a typical experiment run, one of the three scenarios will fail on `respects_nap_window` or `pacing_arc` — usually the one where the constraint surface is tightest. **This is the kind of failure mode the eval catches but the trace alone doesn't tell you about** — and the *variance* itself is a real observation about agent reliability that wouldn't surface without an eval harness.

## Notes on choices

- **Models via LiteLLM proxy.** The OpenAI SDK is pointed at a LiteLLM base URL (`/v1` required — the SDK doesn't auto-add it). Same client serves both the pipeline and the judge.
- **Chroma over FAISS/numpy.** Picked Chroma so the retriever-span attributes match what AX's retrieval-relevance display expects without manual coercion.
- **Constraint extraction is its own span.** Could have been a regex / pydantic-parsed step, but making it an LLM call is more realistic for an agent-style demo and gives a useful eval target.
- **Rank step is pure code.** All hard constraints (age, weather, travel budget) applied here; soft scoring lives here too. The composer agent only sees pre-filtered candidates initially — keeps it focused on assembling a plan rather than re-checking eligibility. It *can* still call `lookup_more_activities` if it wants more.
- **Agentic composer uses tool-calling, not a ReAct text loop.** Each turn is an OpenAI-style `chat.completions` call with `tools=[...]`. `response_format={"type": "json_object"}` coexists with `tools=` on this proxy (when the model wants a tool, it emits `tool_calls` regardless; when it produces a final answer, the content is guaranteed-valid JSON). This combo materially improves final-plan reliability.
- **Travel as soft preference**, not a hard programmatic eval. The pacing judge picks up "too much driving" naturally.
- **Family details anonymized in code** (`Child age 2`, no real names). Activity catalog is real DC venues.
