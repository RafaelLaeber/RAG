"""Configuração da aplicação, lida de variáveis de ambiente e do arquivo .env"""

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações tipadas e validadas da aplicação"""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Segredos (obrigatórios, sem valor padrão)
    openai_api_key: SecretStr
    astra_db_api_endpoint: str
    astra_db_application_token: SecretStr

    # Modelos
    llm_model: str = "gpt-6-luna"
    embedding_model: str = "text-embedding-3-small"

    # Vector Store
    astra_db_collection: str = "documents"

    # Ingestão
    data_dir: Path = Path("data/raw")
    chunk_size: int = Field(default=1000, gt=0)
    chunk_overlap: int = Field(default=150, ge=0)

    # Retriever
    retriever_k: int = Field(default=4, gt=0)

    # Câmbio (AwesomeAPI, sem chave)
    exchange_api_url: str = "https://economia.awesomeapi.com.br/json/last"
    exchange_timeout: float = Field(default=10.0, gt=0)

    # Memória de longo prazo (SQLite local)
    memory_db_path: Path = Path("storage/memory.sqlite")
    memory_max_items: int = Field(default=50, gt=0)
    user_id: str = "colaborador"

    # LangSmith (opcional: sem chave, o tracing fica desligado)
    langsmith_api_key: SecretStr | None = None
    langsmith_project: str = "orbita-agent"


@lru_cache  # Devolve o mesmo objeto sem precisar recriar
def get_settings() -> Settings:
    """Retorna a instância única de Settings, criada só na primeira chamada"""
    return Settings()


def setup_langsmith() -> bool:
    """Liga o tracing do LangSmith se houver chave no .env.

    O LangSmith lê a configuração de os.environ, e o pydantic-settings não
    exporta o .env para lá, então copiamos as variáveis manualmente.

    Returns:
        True se o tracing foi ligado.
    """
    settings = get_settings()
    # Chave ausente ou vazia ("LANGSMITH_API_KEY=" copiado do .env.example) = tracing desligado
    if settings.langsmith_api_key is None or not settings.langsmith_api_key.get_secret_value():
        return False
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key.get_secret_value()
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    return True
