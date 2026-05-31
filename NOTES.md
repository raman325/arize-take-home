# NOTES — raw observations from building this app against Arize AX

> Captured *during* the build, not retro-fitted. Not the final PM deliverable — that comes later. This file is the feedstock: friction points, what worked, and where I'd push back if I were a PM on this team.

## The build, in one paragraph

Built a 6-step DC-weekend-planner **agent** against Arize AX. The final composer step is an autonomous tool-calling loop (OpenInference kind `AGENT`) that can dynamically invoke `lookup_more_activities(query)` to pull more retrieval candidates from the catalog; other steps are LLM / TOOL / RETRIEVER / CHAIN. Four evaluators (2 code, 2 LLM-judge composed via `phoenix.evals.create_classifier`). Both AX workflows exercised: production traces via `scripts/seed_prod_traffic.py`, dataset + experiment + evaluators via `scripts/run_evals.py`. Took roughly half a day. The surprises were almost entirely in *integration*, not in the LLM work.

---

## Three friction points worth pitching against

### F1 — A null eval score returns a 50-line Arrow Flight stack trace

When an evaluator returns `EvaluationResult(score=None)` — for example because the underlying judge classifier failed to parse a label and returned a `Score` with `score=None` — the upload fails server-side with:

> `column "eval.<name>.score": unsupported cast from null to float64: reserved column cannot be coerced to canonical type`

That message arrives wrapped in ~50 lines of pyarrow / Flight gRPC traceback. To diagnose it, you scroll through Arrow internals to find a clean sentence the SDK could have raised client-side with the offending row + evaluator name attached.

The fix is small: validate the evaluator dataframe before the Flight call and raise a domain-native error pointing at the bad cell. Half a day of work for someone who knows the codebase. The user-side cost it eliminates is much larger than that.

**Why this matters as a product opportunity:** the error surfaces in the wrong layer. The user wrote correct Python. One evaluator's return shape is the problem. The error pretends the problem is somewhere deep in transport. Errors should be raised closest to the cause, in the user's vocabulary.

### F2 — Phoenix vs Arize self-hosted vs Arize AX boundaries are unclear

After shipping a working app against AX, I still couldn't write a one-sentence answer to *"if I'm new and want X, do I install Phoenix or Arize?"*. That's a positioning failure, not a docs failure.

Concrete instances I hit:

- Writing an LLM-judge evaluator required `phoenix.evals.create_classifier(...)` *wrapped inside* `arize.experiments.evaluators.base.LLMEvaluator`. Two packages own overlapping concepts (evaluator / classifier / judge LLM) with slightly different shapes. No doc pointed at the layering pattern; I figured it out by reading SDK source.
- `arize.otel.register` vs `phoenix.otel.register`: both real, both feed OTLP, different installs. Running `uv remove arize-phoenix-otel` silently uninstalled `arize_otel` too because it was a transitive dep. That kind of surprise is the symptom of a product surface that hasn't decided how its pieces relate.
- Three products. Partially overlapping SDKs. OpenInference is the actual spec underneath but a first-time user would not know that.

**Two MVP shapes worth pitching:**

1. **Unified SDK.** One Python surface that targets local Phoenix, self-hosted Arize, or AX via a single config switch. OpenInference makes this technically feasible already. Drops the "which package do I install?" question entirely.
2. **Radical clarity.** A single doc page (and a decision tree on the homepage): *"Phoenix is for X. Arize self-hosted is for Y. AX is for Z. They share OpenInference."* Cheaper to ship; reduces first-contact anxiety even without consolidating code.

The "invest in coherence over features" through-line of this file lives here most directly.

### F3.5 — Sibling spans reorder during expand interaction (live UI bug, confirmed pure render-side)

Observed in the trace list view of the `weekend-planner` project, where each trace row has an "Expand child spans" button (visible in DOM as `aria-label="Expand child spans"`) that inlines that trace's children below it.

**The bug, reproducible deterministically:**

A single trace (`saturday_morning_conflict`, root `weekend_planner_pipeline` CHAIN) has 6 children. As I clicked expand buttons, the sibling order changed:

| Step | Action | Resulting order of the last two siblings |
|---|---|---|
| 1 | Expand the root row | `... RETRIEVER → AGENT compose_plan → CHAIN rank_and_filter` |
| 2 | Click "Expand child spans" on `rank_and_filter` (CHAIN) | `... RETRIEVER → **CHAIN rank_and_filter** → AGENT compose_plan` |
| 3 | Click "Expand child spans" on `compose_plan` (AGENT) | `... RETRIEVER → **AGENT compose_plan** → (ChatCompletion child) → CHAIN rank_and_filter` |

**In short: the most-recently-expanded sibling jumps to the higher position in the list.** Even though "expand" is supposed to just reveal children, it changes the position of the row you clicked relative to its siblings.

**Verified pure render-side** by fetching the spans via the Arize SDK (`spans.export_to_df`) and inspecting the data directly. The OpenTelemetry payload is structurally correct:
- All 6 immediate children carry `parent_id` pointing at the root.
- `start_time` ordering chronologically is: extract → weather → calendar → retrieval → rank (CHAIN @ 17:13:12.438286) → compose (AGENT @ 17:13:12.438463). 0.18ms apart but unambiguously ordered.
- AX is using *some* non-chronological default sort in the UI that contradicts the underlying data. There's also a secondary ordering oddity worth noting: even before any swaps, `calendar_lookup` rendered before `weather_lookup` despite weather starting 93µs earlier in the actual data.

That's an important framing: **the bug is in the renderer, not in the customer's instrumentation**. A customer hitting this can't fix it by writing better tracing code.

**Evidence in repo:** `docs/screenshots/ax_trace_reorder_bug.gif` — live screencast of the reorder sequence (today's deliverable site embeds it in the appendix).

There's also a related smaller observation: **every span renders with an expand chevron by default, including leaf nodes**. *"When a tree is actually just a node, they always render as trees."* Even pure-leaf TOOL spans have an expand affordance that, once clicked, reveals nothing (or just the attribute panel). Wastes a click and trains users that "expand" doesn't reliably do anything.

**Why this matters as a product opportunity:**
- **Trust in the trace view erodes fast** when siblings move during interaction. The whole value proposition of a trace is "stable picture of what happened" — reordering breaks that.
- **Every customer building any agent will hit this** the first time they open a trace, because they'll instinctively click around to understand the structure.
- It's a small UX bug with outsized first-impression cost. The kind of thing that's *invisible until you actually use the product to inspect your own work*.

**MVP fix shapes:**
1. **Stable ordering**: lock the sibling order to chronological (or some other stable key) and don't let interactions change it. Cheap fix, big trust win.
2. **Smart expand affordance**: hide the chevron on spans that have no children, or render leaf spans with a distinct visual treatment so users learn the shape at a glance.
3. **Higher-leverage and harder**: a "report this rendering" right-click on the trace view that captures span IDs + viewport state and files an internal ticket. Turns silent frustration into a feedback loop. This is exactly the kind of small affordance that drives compounding product quality over time.

### F3 — UI ↔ code-defined evaluator discoverability gap

Four evaluators live in `evals/`. They produce columns in the AX UI when an experiment runs. **But the UI has no notion that they exist as a thing the project owns.** No "Evaluators" page listing both code-defined and UI-defined evaluators. No badge on the project page that says "this project has 4 evaluators." Asking *"how do I add an evaluator in the UI?"* surfaces the same gap from the other side — UI-defined and code-defined live in separate mental models with no bridge between them.

The worst moment is also the most common one: a user sees a bad output in a trace and wants to add an eval that catches it. Today, they leave the trace view → find the monitors page → click create → manually compose a filter → write a rubric. Multi-step, easy to abandon, and the activation energy is highest at the exact moment users *most need* to act.

**Two MVP shapes:**

1. **Discoverability badge.** On the project page: *"4 code-defined evaluators, 0 UI-defined."* Click → list of both kinds and what they apply to. Zero new infrastructure; bridges the two worlds.
2. **From-trace-to-monitor.** Right-click a bad span → *"create monitor from this."* The UI prefills the filter (`span_kind=LLM`, `name=compose_plan`) and suggests a rubric template seeded from the span's input/output. Collapses ~5 clicks into 1.

---

## Prompt Playground walkthrough (UI flow, live observations)

Ran the dataset through the no-code Playground after the code-driven experiments. Notes captured live, not retro-fitted:

**What worked well:**
- **Dataset columns auto-detected as template variables.** Typed `{family_request}` into the prompt and it auto-bound to the dataset column without any setup. Genuinely delightful first-touch UX.
- **Side-by-side per-row outputs** with avg latency + avg tokens displayed inline. The grid view makes it instantly obvious which row is slow / cheap / weird without leaving the page.
- **"Recent runs for this view"** panel in the top right that shows your previous Playground runs and their experiment names — survives page refresh, makes iteration legible.
- **BYOK works.** I switched the default provider to my own LiteLLM proxy + glm-6.1 model and it just worked. (Initial run failed with a stale API key error; reconfiguring and rerunning was straightforward.)
- **The evaluator template library is genuinely good.** 12 LLM-as-judge templates (RAG Relevancy, Hallucination, Tool Calling, Q&A, Summarization, Toxicity, User Frustration, SQL Generation, Code Functionality, Code Readability, Human vs AI, Reference Link Correctness) plus 2 code-evaluator templates (Contains all/any Keyword). Each template card lists its expected input variables inline. Directly addresses the "writing rubrics is hand-craft" friction for the *common* eval patterns.

**Friction worth investing in:**
- **Templates assume specific data shapes that don't fit agent apps with internal retrieval.** RAG Relevancy expects `{input}` and `{reference}` columns — but in my agent, retrieval happens *inside* the compose step, so there's no "reference text" exposed to the Playground. To use the template I'd have to restructure my dataset OR write a custom rubric from scratch. The product asks the customer to bend their data to the template; it should be the other way around. **Two MVP shapes to pitch:**
  1. **Template forking** — "Use this template as a starting point" → opens the prompt+choices in the custom editor with variable names editable. Lower the cost of customization without rewriting from scratch.
  2. **Data-aware template suggestions** — Playground looks at your dataset columns + sample task output, and suggests which templates fit + which need variable remapping. Closes the loop between dataset shape and template library.
- **The Playground evaluator templates don't surface my 4 code-defined evaluators** as starting points or comparison candidates. The two worlds (UI templates vs code-defined evaluators) are completely siloed in the same UI. Reinforces F3 — discoverability gap is real.
- **An "Are you sure you want to set default AI provider?" modal pops up on Run** with two options ("Don't show this again" — wait, I actually mis-read the button text initially; it was "Dismiss" + "Save Default"). Modal friction at the moment you want to test, not before you want to test. Move it to a settings nudge or onboarding screen instead.

**Cross-cut takeaway from this walkthrough:** the Playground is a strong product surface on its own. Its weakness isn't the surface itself; it's how it relates to the rest of AX (templates not fitting agent apps, no awareness of code evaluators, friction modals at action time). Coherence problem, not feature problem — same theme as the F2 boundaries finding.

## Online Evaluator walkthrough (UI flow, live observations)

After the Playground, walked the production-side observability flow: setting up automated scoring of incoming traces.

**The naming problem.** Started at the **Monitors** page expecting to find LLM-eval-on-prod-traffic setup. The empty state offered only two templates: **Latency Monitor** and **Token Count Monitor** — both metric-based alerts on numeric span fields. No way to attach an LLM judge here. Bounced back, found "+ Add Online Evaluator" on the project's trace page — *that's* the actual surface.

So there are two distinct concepts:
- **Monitors** = metric-based alerts (latency, tokens) — set alerts and get pinged when they spike
- **Online Evaluators** = LLM-as-judge or code-based eval, sampled, on incoming traces — continuously score the traffic

That distinction is real and useful once you understand it, but **the naming and discoverability work against the user**. "Monitor my production traffic with an LLM judge" is the natural mental model. Most users probably arrive at Monitors first, hit a dead end, and might not find Online Evaluators without help. (I gave you wrong directions on this earlier in our session — that's the same mistake a customer would make.)

**MVP fix shapes:**
1. **Rename or unify**: either rename "Online Evaluators" to "Eval Monitors" (or rename Monitors to "Metric Alerts") so the naming is parallel. Easier path: a "Monitor with LLM Eval" template in the Monitors empty state that deep-links into the Online Evaluator surface, so the natural starting point gets the user where they need to go.
2. **Cross-reference in empty states**: the Monitors empty state should explicitly say "Looking to run LLM evals on production traces? Go to a project page and click 'Add Online Evaluator'." Cheap copy fix; bridges the gap.

**What works well in the Online Evaluator surface:**
- Same evaluator authoring UX as the Playground (good reuse — author once, the form looks the same in both contexts).
- **Production controls are there and well-designed**: `Run Continuously` toggle, `Sampling Rate (%)`, `One-Time Backfill`. All the right knobs.
- **Preview pane on the right shows live spans the evaluator will run against** before you commit. Great trust-building feature — you can verify the data shape matches your eval's variables before turning it on.
- **"Create Via Alyx"** AI-assisted evaluator authoring is offered as a third option alongside LLM-As-A-Judge and Code Evaluator. Directly addresses the "rubrics are hand-craft" friction. Didn't try it in depth, but worth highlighting as a thing AX already invested in — relevant for the proposal if you want to position F2 (boundaries) and the F3 family (discoverability) as the bigger gaps rather than rubric authoring per se.

**Cross-cut takeaway:** the technical surface for online evals is genuinely capable. The product gap is **how a new user finds it** — which is the same coherence problem as F3 (UI ↔ code-evaluator discoverability) and F2 (Phoenix/Arize/AX boundaries). The pattern keeps repeating: AX has the right primitives; they're not stitched together in a way that matches how customers think.

## Other observations from the build

These didn't make the top three but are useful framing for any proposal discussion.

- **Task signature binding by parameter name.** `experiments.run(task=...)` binds the task function's parameter name to one of `{input, output, metadata, dataset_row}`. Nested dicts in dataset rows get silently stringified to JSON. I had to read `arize.experiments.functions._bind_task_signature` to figure it out. A strongly-typed `Example` dataclass with an explicit `task.bind(...)` decorator would be friendlier.
- **Beta API churn in a v8.x SDK.** `datasets.list`, `datasets.create`, `experiments.list_runs` all warn `[BETA]`. `list_runs` returns data that fails its own pydantic validation. Betas either need to graduate or shouldn't be reachable from the main client surface.
- **OpenAI SDK `/v1` gotcha at the LiteLLM boundary.** Without `/v1` on the base URL, calls land on the auth proxy's HTML login page and the SDK returns the HTML as a string with `type: str`. Not Arize's bug, but representative — LiteLLM-proxy is the most common BYOM path, and a doc snippet on "common BYOM gotchas" would save customers an hour each.
- **Writing a rubric is hand-craft.** I wrote ~12 lines of pacing-arc rubric and have no objective way to know it's a good one. *"Run the rubric against N labeled examples and tell me precision/recall"* is exactly the kind of UI workflow an AX customer would want — and arguably the highest-leverage thing on this whole list.
- **The eval harness surfaces failures the trace alone wouldn't show.** A given experiment run will have one or two scenarios fail an evaluator — usually `respects_nap_window` or `pacing_arc` on whichever scenario has the tightest constraint surface that run. Which scenario fails *varies between runs* because the agent's path isn't deterministic. That variance is itself an observation: agent reliability has a distribution, not a value, and the eval column tells you the shape of it across runs.
- **Tool-calling × `response_format={"type":"json_object"}` works together on this proxy** but isn't a documented combination. Without `response_format`, the agent produced plans with missing fields ~30% of the time on the same scenarios. The two constraints layer cleanly: `tool_calls` wins when the model wants a tool; JSON wins when it doesn't. Worth flagging as a "this combo unlocks reliable agentic JSON output" doc snippet.
- **Agent JSON output reliability is hand-craft work.** Even with `response_format={"type":"json_object"}`, I needed three separate guards to keep the pipeline from crashing on agent output: (a) zero-pad time strings (`"9:00"` → `"09:00"`) before pydantic parses them, (b) strip ```json``` markdown fences in case the model wraps the JSON, (c) skip malformed slots rather than crash the whole plan. None of these are unique to my app — every Arize customer with a structured-output agent will hit the same three. AX could ship an opinionated "structured agent output" validator/cleaner with these defaults baked in.

---

## What worked well (lead with this, don't bury it)

- **`arize.otel.register(...)` was a 5-line setup**, no manual exporter config. Hit the gold path immediately. Worth complimenting — it's the standard the rest of the SDK should hit.
- **OpenInference span attributes for retrieval** rendered correctly in AX with zero coercion code on my side. `retrieval.documents.{i}.document.{id,content,score,metadata}` just worked.
- **`BatchSpanProcessor` defaults are sensible**, modulo a small `time.sleep(2)` at the end of short CLI runs to allow the flush. Worth either documenting or auto-flushing on `atexit`.
- **Experiment results landed without me hand-managing span↔experiment-run linkage.** The SDK linked them under the hood; the UI knows where each eval came from. This is a real product win.

---

## Cross-cutting observation

The most painful integrations in this build came from **two adjacent product surfaces with overlapping concepts and slightly-different shapes**:
- Phoenix evals + Arize evaluators
- `arize-otel` vs `arize-phoenix-otel`
- UI evaluators vs code evaluators

Each individually is fine. Collectively, the integration tax shows up as *"I don't know if I'm doing this the recommended way."* That's the through-line of any proposal that comes out of this build: **invest in coherence, not features**.

---

## TODO before the final deck

- [ ] Screenshots: trace view (one root span expanded), experiment results table (with `saturday_morning_conflict.needs_work` cell visible), Datasets list
- [ ] Pick the deliverable format: Figma mock, Excalidraw architecture diagram, written doc, or live demo backed by this repo
- [ ] Pick the 1 MVP to lead with (current leading candidate: F3.2 — *from-trace-to-monitor* — because it has the strongest "obviously needed once you see it" quality and the lowest implementation risk)
- [ ] Sketch the architecture-diagram side: where the new feature sits relative to current Monitors / Experiments / Spans surfaces
