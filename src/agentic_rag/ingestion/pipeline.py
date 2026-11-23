"""Pipeline de ingestão: carregar, dividir e indexar os documentos no vector store."""

import hashlib
import logging

from langchain_core.documents import Document
from langsmith import traceable

from agentic_rag.config import get_settings, setup_langsmith
from agentic_rag.ingestion.loaders import load_documents
from agentic_rag.ingestion.splitter import split_documents
from agentic_rag.ingestion.tracing import summarize_documents
from agentic_rag.retrieval.vectorstore import get_vector_store

logger = logging.getLogger(__name__)


def _chunk_id(chunk: Document) -> str:
    """Gera um ID estável a partir da origem e do conteúdo do chunk"""
    key = f"{chunk.metadata['source']}|{chunk.metadata.get('page')}|{chunk.page_content}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


@traceable(
    run_type="chain",
    name="index_chunks",
    process_inputs=lambda inputs: {"chunks": summarize_documents(inputs["chunks"])},
)
def _index_chunks(chunks: list[Document]) -> int:
    """Envia os chunks ao vector store; os embeddings aparecem como runs filhos."""
    vector_store = get_vector_store()
    vector_store.add_documents(chunks, ids=[_chunk_id(chunk) for chunk in chunks])
    return len(chunks)


@traceable(run_type="chain", name="ingestion", tags=["ingestion"])
def run_ingestion() -> int:
    """Executa a ingestão completa dos documentos configurados no Settings

    Rodar mais de uma vez não duplica os chunks: cada chunk tem um ID estável e o vector sore
    sobrescreve o resgistro existente.

    Returns:
        Quantidade de chunks enviados ao vector store.
    """

    settings = get_settings()

    documents = load_documents(settings.data_dir)
    chunks = split_documents(documents, settings.chunk_size, settings.chunk_overlap)

    for chunk in chunks:
        chunk.metadata["embedding_model"] = settings.embedding_model

    total = _index_chunks(chunks)

    logger.info("Ingestão concluida: %d chunk(s) indexados", total)
    return total


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    setup_langsmith()
    run_ingestion()
