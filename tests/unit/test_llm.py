"""Testes das factories de modelos."""

import pytest
from pydantic import SecretStr

from agentic_rag import llm
from agentic_rag.config import Settings


@pytest.fixture
def patched_settings(monkeypatch: pytest.MonkeyPatch, test_settings: Settings) -> Settings:
    """Faz o módulo llm usar o Settings falso"""
    monkeypatch.setattr(llm, "get_settings", lambda: test_settings)
    return test_settings


def test_get_chat_model_uses_settings(patched_settings: Settings) -> None:
    model = llm.get_chat_model()

    assert model.model_name == patched_settings.llm_model
    assert isinstance(model.openai_api_key, SecretStr)
    assert model.openai_api_key.get_secret_value() == "sk-test"
    assert model.max_retries == 2


def test_get_embeddings_uses_settings(patched_settings: Settings) -> None:
    embeddings = llm.get_embeddings()

    assert embeddings.model == patched_settings.embedding_model
    assert isinstance(embeddings.openai_api_key, SecretStr)
    assert embeddings.openai_api_key.get_secret_value() == "sk-test"
