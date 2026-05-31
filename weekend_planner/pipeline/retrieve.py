"""Step 4 — Activity retrieval. RETRIEVER span.

A persistent on-disk Chroma collection. The first call seeds it from the
ACTIVITIES catalog; subsequent calls reuse the embeddings (cuts a chunk of
cost off the dev workflow when you iterate).
"""

from __future__ import annotations

from pathlib import Path

import chromadb
from openinference.semconv.trace import OpenInferenceSpanKindValues

from ..config import load_settings
from ..data.activities import ACTIVITIES, ACTIVITIES_BY_ID
from ..llm_client import get_client
from ..schemas import RetrievedActivity
from ..tracing import set_output, set_retrieval_documents, span

_COLLECTION_NAME = "activities"
_PERSIST_DIR = Path("chroma_store")


def _embed(texts: list[str]) -> list[list[float]]:
    s = load_settings()
    r = get_client().embeddings.create(model=s.embedding_model, input=texts)
    return [d.embedding for d in r.data]


def _get_or_seed_collection() -> chromadb.Collection:
    _PERSIST_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(_PERSIST_DIR))
    collection = client.get_or_create_collection(
        name=_COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    if collection.count() == len(ACTIVITIES):
        return collection
    # Reseed (covers both empty and partial-load cases).
    if collection.count() > 0:
        client.delete_collection(_COLLECTION_NAME)
        collection = client.get_or_create_collection(
            name=_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
    docs = [f"{a.name}. {a.description}" for a in ACTIVITIES]
    embeddings = _embed(docs)
    collection.add(
        ids=[a.id for a in ACTIVITIES],
        documents=docs,
        embeddings=embeddings,
        metadatas=[
            {
                "indoor": a.indoor,
                "min_age_years": a.min_age_years,
                "max_age_years": a.max_age_years,
                "typical_duration_min": a.typical_duration_min,
                "travel_minutes_from_home": a.travel_minutes_from_home,
                "tags": ",".join(a.tags),
            }
            for a in ACTIVITIES
        ],
    )
    return collection


def retrieve_activities(query: str, *, top_k: int = 8) -> list[RetrievedActivity]:
    """Embed the query, fetch top_k nearest activities, emit a RETRIEVER span."""
    with span("activity_retrieval", OpenInferenceSpanKindValues.RETRIEVER, input_value=query) as s:
        collection = _get_or_seed_collection()
        [query_embedding] = _embed([query])
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "distances", "metadatas"],
        )

        ids = (results["ids"] or [[]])[0]
        distances = (results["distances"] or [[]])[0]
        documents = (results["documents"] or [[]])[0]

        retrieved: list[RetrievedActivity] = []
        span_docs: list[dict] = []
        for activity_id, distance, content in zip(ids, distances, documents):
            activity = ACTIVITIES_BY_ID[activity_id]
            # Chroma cosine "distance" is 1 - cosine_similarity; convert back.
            score = max(0.0, 1.0 - float(distance))
            retrieved.append(RetrievedActivity(activity=activity, similarity_score=score))
            span_docs.append(
                {
                    "id": activity_id,
                    "content": content,
                    "score": score,
                    "metadata": {
                        "indoor": activity.indoor,
                        "tags": activity.tags,
                    },
                }
            )
        set_retrieval_documents(s, span_docs)
        set_output(s, {"count": len(retrieved), "ids": ids})
        return retrieved
