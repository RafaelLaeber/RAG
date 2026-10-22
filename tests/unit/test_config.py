"""Testes de configuração da aplicação"""

import pytest
from pydantic import ValidationError

from agentic_rag.config import Settings


def test_settings_reads_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ASTRA_DB_API_ENDPOINT", "https://example.com")
    monkeypatch.setenv("ASTRA_DB_APPLICATION_TOKEN", "AstraCS:test")

    settings = Settings(_env_file=None)

    assert settings.openai_api_key.get_secret_value() == "sk-test"
    assert settings.embedding_model == "text-embedding-3-small"


def test_settings_fails_without_required_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ASTRA_DB_API_ENDPOINT", raising=False)
    monkeypatch.delenv("ASTRA_DB_APPLICATION_TOKEN", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
