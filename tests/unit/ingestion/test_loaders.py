"""Testes do carregamento de documentos."""

from pathlib import Path

import pytest

from agentic_rag.ingestion.loaders import load_documents


def test_load_documents_reads_supported_files(tmp_path: Path) -> None:
    (tmp_path / "manual.md").write_text("# Manual\nConteúdo do manual.", encoding="utf-8")
    (tmp_path / "faq.txt").write_text("Pergunta e resposta.", encoding="utf-8")

    documents = load_documents(tmp_path)

    assert len(documents) == 2
    assert {doc.metadata["source"] for doc in documents} == {"manual.md", "faq.txt"}
    assert {doc.metadata["file_type"] for doc in documents} == {"md", "txt"}


def test_load_documents_ignores_unsupported_files(tmp_path: Path) -> None:
    (tmp_path / "planilha.csv").write_text("a,b,c", encoding="utf-8")

    assert load_documents(tmp_path) == []


def test_load_documents_fails_when_directory_does_not_exist(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_documents(tmp_path / "nao_existe")
