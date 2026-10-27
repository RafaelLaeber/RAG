"""Fixtures compartilhadas entre os testes."""

import pytest

from agentic_rag.config import Settings


@pytest.fixture
def test_settings() -> Settings:
    """Settings com valores falsos, sem ler o .env."""
    return Settings(
        _env_file=None,
        openai_api_key="sk-test",
        astra_db_api_endpoint="https://example.com",
        astra_db_application_token="AstraCS:test",
    )
