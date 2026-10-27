"""Factory do vector store (AstraDB)"""

from langchain_astradb import AstraDBVectorStore
from langchain_core.vectorstores import VectorStore

from agentic_rag.config import get_settings
from agentic_rag.llm import get_embeddings


def get_vector_store() -> VectorStore:
    """Conecta ao Astra DB, criando a collection se ela ainda não existir

    Returns:
        Vector Store ligado à collection configurada no Settings
    """

    settings = get_settings()
    return AstraDBVectorStore(
        collection_name=settings.astra_db_collection,
        embedding=get_embeddings(),
        api_endpoint=settings.astra_db_api_endpoint,
        token=settings.astra_db_application_token.get_secret_value(),
        metric="cosine",
    )
