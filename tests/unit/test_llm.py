"""Testes das factories de modelos."""

import pytest

from agentic_rag import llm
from agentic_rag.config import Settings


@pytest.fixture
def fake_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    settings = Settings(
        _env_file=None,
        openai_api_key="sk-test",
        astra_db_api_endpoint="https://example.com",
        astra_db_application_token="AstraCS:test",
    )
    monkeypatch.setattr(llm, "get_settings", lambda: settings)
    return settings


def test_get_chat_model_uses_settings(fake_settings: Settings) -> None:
    model = llm.get_chat_model()

    assert model.model_name == fake_settings.llm_model
    assert model.openai_api_key is not None
    assert model.openai_api_key.get_secret_value() == "sk-test"
    assert model.max_retries == 2


def test_get_embeddings_uses_settings(fake_settings: Settings) -> None:
    embeddings = llm.get_embeddings()

    assert embeddings.model == fake_settings.embedding_model
    assert embeddings.openai_api_key is not None
    assert embeddings.openai_api_key.get_secret_value() == "sk-test"
