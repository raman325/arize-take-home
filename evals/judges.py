"""LLM-as-judge evaluators using `phoenix.evals` for the underlying judge
LLM, wrapped in arize.experiments LLMEvaluator subclasses for transport.

Why two libraries here:
- `phoenix.evals.create_classifier` is the modern Phoenix way to express a
  rubric + choices + LLM together as a callable. It handles prompt
  templating, response parsing, and per-choice scoring.
- `arize.experiments.evaluators.base.LLMEvaluator` is what `experiments.run`
  expects to receive. It's a thin abstract base — we just delegate to the
  Phoenix classifier inside `evaluate()`.

That layering keeps the judge prompt + parsing in the well-tested Phoenix
classifier, while still slotting cleanly into the Arize experiment flow.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from arize.experiments.evaluators.base import (
    EvaluationResult,
    LLMEvaluator,
)
from phoenix.evals import LLM, create_classifier

from weekend_planner.config import load_settings


@lru_cache(maxsize=1)
def _judge_llm() -> LLM:
    s = load_settings()
    creds = {"base_url": s.litellm_base_url, "api_key": s.litellm_api_key}
    return LLM(
        provider="openai",
        model=s.judge_model,
        sync_client_kwargs=creds,
        async_client_kwargs=creds,
    )


_PACING_RUBRIC = """\
You are reviewing a weekend plan for a family with a 2-year-old.

Rate the plan's PACING ARC. A good pacing arc has:
- The most physically/cognitively demanding activity in the MORNING (before the nap),
- Lower-energy or restful activity AFTER the nap,
- Slots NOT crammed back-to-back (room for transitions),
- A balanced load across Saturday vs Sunday (not all on one day).

If most of those hold: respond "good".
If multiple are violated (e.g. high-energy after the nap, or back-to-back demanding activities): respond "needs_work".

Plan:
{plan_json}

Family request (for context):
{request}
"""


_RETRIEVAL_RELEVANCE_RUBRIC = """\
You are judging whether a retrieved activity is RELEVANT to a family's weekend planning query.

Query:
{query}

Retrieved activity:
{activity}

Mark "relevant" if the activity could plausibly appear in a good plan for this family
(right age range OR right weather OR matches a stated preference). Mark "irrelevant"
only if it clearly doesn't belong (wrong age range AND wrong weather, or off-topic entirely).

Respond with one word: "relevant" or "irrelevant".
"""


@lru_cache(maxsize=1)
def _pacing_classifier():
    return create_classifier(
        name="pacing_arc",
        prompt_template=_PACING_RUBRIC,
        llm=_judge_llm(),
        choices={"good": 1.0, "needs_work": 0.0},
    )


@lru_cache(maxsize=1)
def _retrieval_relevance_classifier():
    return create_classifier(
        name="retrieval_relevance",
        prompt_template=_RETRIEVAL_RELEVANCE_RUBRIC,
        llm=_judge_llm(),
        choices={"relevant": 1.0, "irrelevant": 0.0},
    )


def _scores_to_result(scores: list[Any], fallback_label: str) -> EvaluationResult:
    """phoenix.evals returns a list[Score] from .evaluate() — collapse to one.

    Defensive: classifier failures (rate limit, JSON parse miss) come back as
    Scores with .score=None and an .explanation message. We coerce to 0.0 so
    the Arize Arrow-Flight upload (which rejects nulls in eval.*.score) succeeds.
    """
    if not scores:
        return EvaluationResult(
            score=0.0, label=fallback_label,
            explanation="classifier returned no scores", metadata={},
        )
    s = scores[0]
    raw_score = getattr(s, "score", None)
    return EvaluationResult(
        score=float(raw_score) if raw_score is not None else 0.0,
        label=getattr(s, "label", None) or fallback_label,
        explanation=getattr(s, "explanation", None) or "",
        metadata={},
    )


class PacingArcEval(LLMEvaluator):
    """Rates the plan's pacing arc (morning-energy / post-nap-rest)."""

    _name = "pacing_arc"

    def evaluate(self, *, input=None, output=None, **_) -> EvaluationResult:
        import json

        plan_json = json.dumps((output or {}).get("plan", {}), indent=2)
        request = (input or {}).get("family_request", "")
        scores = _pacing_classifier().evaluate(
            {"plan_json": plan_json, "request": request}
        )
        return _scores_to_result(scores, fallback_label="needs_work")


class RetrievalPrecisionEval(LLMEvaluator):
    """Per-doc relevance judge, aggregated to precision@k for the row.

    Asks the judge to label each retrieved activity relevant/irrelevant
    against the retrieval query, then reports the fraction labeled
    relevant. Per-doc labels are kept in metadata so they're inspectable
    in the AX UI even though the score is a single aggregate.
    """

    _name = "retrieval_precision"

    def evaluate(self, *, output=None, **_) -> EvaluationResult:
        retrieved = (output or {}).get("retrieved", [])
        query = (output or {}).get("retrieval_query", "")
        if not retrieved:
            return EvaluationResult(
                score=0.0, label="empty",
                explanation="no documents retrieved",
                metadata={},
            )
        classifier = _retrieval_relevance_classifier()
        per_doc: list[dict] = []
        for doc in retrieved:
            activity_str = (
                f"{doc.get('name', '')} (id={doc.get('id', '')}, "
                f"indoor={doc.get('indoor', '?')}, "
                f"ages {doc.get('min_age', '?')}-{doc.get('max_age', '?')}): "
                f"{doc.get('description', '')}"
            )
            scores = classifier.evaluate({"query": query, "activity": activity_str})
            s = scores[0] if scores else None
            raw_score = getattr(s, "score", None) if s else None
            per_doc.append(
                {
                    "id": str(doc.get("id", "")),
                    "label": (getattr(s, "label", "") or "") if s else "",
                    "score": float(raw_score) if raw_score is not None else 0.0,
                }
            )
        relevant = sum(1 for d in per_doc if float(d["score"]) >= 0.5)
        precision = relevant / len(per_doc)
        return EvaluationResult(
            score=precision,
            label="pass" if precision >= 0.7 else "fail",
            explanation=(
                f"{relevant}/{len(per_doc)} retrieved activities judged relevant"
            ),
            metadata={"per_doc": per_doc},
        )
