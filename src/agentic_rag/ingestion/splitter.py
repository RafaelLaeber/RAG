"""Divisão dos documentos em chunks"""

import logging

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langsmith import traceable

from agentic_rag.ingestion.tracing import summarize_documents

logger = logging.getLogger(__name__)


@traceable(
    run_type="chain",
    name="split_documents",
    process_inputs=lambda inputs: {
        "documents": summarize_documents(inputs["documents"]),
        "chunk_size": inputs["chunk_size"],
        "chunk_overlap": inputs["chunk_overlap"],
    },
    process_outputs=summarize_documents,
)
def split_documents(
    documents: list[Document], chunk_size: int, chunk_overlap: int
) -> list[Document]:
    """Divide os documentos em chunks menores, preservando os metadados

    Args:
    documents: Documentos carregados pelos loaders
    chunk_size: Tamanho máximo de cada chunk, em caracteres.
    chunk_overlap: Quantidade de caracteres repetidos entre chunks vizinhos.

    Returns:
    Lista de chunks, cada um com os metadados do documento de origem.
    """

    splitters = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        add_start_index=True,
    )

    chunks = splitters.split_documents(documents)
    logger.info("%d documento(s) divididos em %d chunk(s)", len(documents), len(chunks))
    return chunks
