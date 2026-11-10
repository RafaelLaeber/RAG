"""Tool de RAG: busca nas políticas e documentos internos da Órbita"""

from functools import lru_cache

from langchain_core.documents import Document
from langchain_core.tools import tool
from langchain_core.vectorstores import VectorStoreRetriever

from agentic_rag.retrieval.retriever import get_retriever


@lru_cache  # Conecta ao Astra uma vez só, na primeira busca
def _retriever() -> VectorStoreRetriever:
    return get_retriever()


def _format_docs(docs: list[Document]) -> str:
    """Junta os trechos com a fonte de cada um, para o agente poder citar."""
    if not docs:
        return "Nenhum trecho relevante encontrado."
    return "\n\n---\n\n".join(
        f"[Fonte: {doc.metadata.get('source', 'desconhecida')}]\n{doc.page_content}" for doc in docs
    )


@tool
def search_policies(query: str) -> str:
    """Busca nas políticas e documentos internos da Órbita (reembolso, manual do colaborador, FAQ).

    Use para qualquer pergunta sobre regras, limites, prazos ou procedimentos da empresa.

    Args:
        query: Pergunta ou termos de busca em linguagem natural.
    """
    return _format_docs(_retriever().invoke(query))
