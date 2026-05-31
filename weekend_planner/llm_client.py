"""Single OpenAI-SDK client pointed at the LiteLLM proxy.

The OpenAIInstrumentor (auto-instrument, set up in tracing.py) wraps this
client globally — so every chat.completions / embeddings call from anywhere
in the app emits an LLM-kind span with token counts, cost, and latency.
"""

from __future__ import annotations

from functools import lru_cache

from openai import OpenAI

from .config import load_settings


@lru_cache(maxsize=1)
def get_client() -> OpenAI:
    s = load_settings()
    return OpenAI(base_url=s.litellm_base_url, api_key=s.litellm_api_key)
