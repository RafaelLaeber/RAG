"""Resumos dos dados da ingestão para o LangSmith (evita enviar o texto inteiro dos documentos)."""

from typing import Any

from langchain_core.documents import Document


def summarize_documents(documents: list[Document]) -> dict[str, Any]:
    """Quantidade de documentos/chunks e as fontes de origem."""
    sources = sorted({str(doc.metadata.get("source", "?")) for doc in documents})
    return {"count": len(documents), "sources": sources}
