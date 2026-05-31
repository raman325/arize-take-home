"""Environment-driven configuration. Loads .env via python-dotenv on import."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Missing required env var: {name}. "
            "Copy .env.example to .env and fill it in."
        )
    return value


@dataclass(frozen=True)
class Settings:
    litellm_base_url: str
    litellm_api_key: str
    pipeline_model: str
    judge_model: str
    embedding_model: str
    arize_space_id: str
    arize_api_key: str
    arize_project_name: str


def load_settings() -> Settings:
    return Settings(
        litellm_base_url=_required("LITELLM_BASE_URL"),
        litellm_api_key=_required("LITELLM_API_KEY"),
        pipeline_model=_required("PIPELINE_MODEL"),
        judge_model=_required("JUDGE_MODEL"),
        embedding_model=_required("EMBEDDING_MODEL"),
        arize_space_id=_required("ARIZE_SPACE_ID"),
        arize_api_key=_required("ARIZE_API_KEY"),
        arize_project_name=os.environ.get("ARIZE_PROJECT_NAME", "weekend-planner"),
    )
