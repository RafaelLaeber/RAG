"""Configuração da aplicação, lida de variáveis de ambiente e do arquivo .env"""

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


@lru_cache  # Devolve o mesmo objeto sem precisar recriar
def get_settings() -> Settings:
    """Retorna a instância única de Settings, criada só na primeira chamada"""
    return Settings()
