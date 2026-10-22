"""Embedding client helpers shared by onboarding and runtime retrieval."""

from __future__ import annotations

from langchain_openai import OpenAIEmbeddings

from app.core.config import Settings


def build_embedding_client(settings: Settings) -> OpenAIEmbeddings | None:
    if (
        not settings.sql_agent_embedding_api_key
        or not settings.sql_agent_embedding_base_url
        or not settings.sql_agent_embedding_model
    ):
        return None
    return OpenAIEmbeddings(
        model=settings.sql_agent_embedding_model,
        openai_api_key=settings.sql_agent_embedding_api_key,
        openai_api_base=settings.sql_agent_embedding_base_url,
        dimensions=settings.sql_agent_embedding_dimension,
        check_embedding_ctx_length=False,
    )
