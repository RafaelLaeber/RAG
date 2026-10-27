"""Testes do pipeline de ingestão."""

from pathlib import Path

import pytest
from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_core.vectorstores import InMemoryVectorStore

from agentic_rag.config import Settings
from agentic_rag.ingestion import pipeline


@pytest.fixture
def vector_store(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, test_settings: Settings
) -> InMemoryVectorStore:
    """Prepara o pipeline com documentos temporários e um vector store em memória."""
    (tmp_path / "manual.md").write_text("Conteúdo do manual. " * 100, encoding="utf-8")
    settings = test_settings.model_copy(update={"data_dir": tmp_path})
    store = InMemoryVectorStore(embedding=DeterministicFakeEmbedding(size=8))

    monkeypatch.setattr(pipeline, "get_settings", lambda: settings)
    monkeypatch.setattr(pipeline, "get_vector_store", lambda: store)
    return store


def test_run_ingestion_indexes_all_chunks(vector_store: InMemoryVectorStore) -> None:
    total = pipeline.run_ingestion()

    assert total > 1
    assert len(vector_store.store) == total


def test_run_ingestion_does_not_duplicate_chunks(vector_store: InMemoryVectorStore) -> None:
    pipeline.run_ingestion()
    total = pipeline.run_ingestion()

    assert len(vector_store.store) == total
