"""Testes da factory do vector store."""

from typing import Any

import pytest

from agentic_rag.config import Settings
from agentic_rag.retrieval import vectorstore


class FakeAstraDBVectorStore:
    """Substitui o AstraDBVectorStore, guardando os argumentos recebidos."""

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


def test_get_vector_store_uses_settings(
    monkeypatch: pytest.MonkeyPatch, test_settings: Settings
) -> None:
    monkeypatch.setattr(vectorstore, "get_settings", lambda: test_settings)
    monkeypatch.setattr(vectorstore, "get_embeddings", lambda: "fake-embeddings")
    monkeypatch.setattr(vectorstore, "AstraDBVectorStore", FakeAstraDBVectorStore)

    store = vectorstore.get_vector_store()

    assert isinstance(store, FakeAstraDBVectorStore)
    assert store.kwargs["collection_name"] == "documents"
    assert store.kwargs["token"] == "AstraCS:test"
    assert store.kwargs["metric"] == "cosine"
    assert store.kwargs["embedding"] == "fake-embeddings"
