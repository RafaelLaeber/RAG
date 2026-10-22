"""Factories dos modelos da OpenAI (chat e embeddings)"""

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from agentic_rag.config import get_settings


def get_chat_model() -> ChatOpenAI:
    """Cria o modelo de chat configurano no Settings"""
    settings = get_settings()
    return ChatOpenAI(
        model=settings.llm_model,
        openai_api_key=settings.openai_api_key,
        timeout=30,
        max_retries=2,
    )


def get_embeddings() -> OpenAIEmbeddings:
    """Cria o modelo de embeddings configurado no Settings."""
    settings = get_settings()
    return OpenAIEmbeddings(model=settings.embedding_model, openai_api_key=settings.openai_api_key)
