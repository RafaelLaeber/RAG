"""Factory do retriever sobre as políticas da Órbita"""

from langchain_core.vectorstores import VectorStoreRetriever

from agentic_rag.config import get_settings
from agentic_rag.retrieval.vectorstore import get_vector_store

# Exclui só documentos sabidamente desatualizados; documentos sem "status" (ex.: o PDF) continuam
EXCLUDE_REPLACED: dict[str, dict[str, str]] = {"status": {"$ne": "substituida"}}


def get_retriever() -> VectorStoreRetriever:
    """Cria o retriever por similaridade, ignorando políticas substituídas.

    Returns:
        Retriever que devolve os k chunks mais parecidos com a pergunta.
    """
    settings = get_settings()
    return get_vector_store().as_retriever(
        search_type="similarity",
        search_kwargs={"k": settings.retriever_k, "filter": EXCLUDE_REPLACED},
    )
