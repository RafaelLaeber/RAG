"""Testes da divisão de documentos em chunks."""

from langchain_core.documents import Document

from agentic_rag.ingestion.splitter import split_documents


def test_split_documents_respects_chunk_size() -> None:
    document = Document(page_content="palavra " * 200, metadata={"source": "teste.md"})

    chunks = split_documents([document], chunk_size=100, chunk_overlap=20)

    assert len(chunks) > 1
    assert all(len(chunk.page_content) <= 100 for chunk in chunks)


def test_split_documents_keeps_metadata() -> None:
    document = Document(page_content="palavra " * 200, metadata={"source": "teste.md"})

    chunks = split_documents([document], chunk_size=100, chunk_overlap=20)

    assert all(chunk.metadata["source"] == "teste.md" for chunk in chunks)
    assert all("start_index" in chunk.metadata for chunk in chunks)
