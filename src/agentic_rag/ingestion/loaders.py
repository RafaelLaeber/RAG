"""Carregamento dos documentos de entrada (.md, .txt e .pdf)."""

import logging
from pathlib import Path

from langchain_core.documents import Document
from pypdf import PdfReader

logger = logging.getLogger(__name__)

TEXT_EXTENSIONS = {".md", ".txt"}
PDF_EXTENSIONS = {".pdf"}


def _load_text(path: Path) -> list[Document]:
    """Carrega um arquivo de texto como um único documento."""
    content = path.read_text(encoding="utf-8")
    return [Document(page_content=content, metadata={"source": path.name})]


def _load_pdf(path: Path) -> list[Document]:
    """Carrega um PDF, gerando um documento por página com texto."""
    reader = PdfReader(path)
    documents = []
    for number, page in enumerate(reader.pages, start=1):
        text = page.extract_text()
        if text.strip():
            documents.append(
                Document(page_content=text, metadata={"source": path.name, "page": number})
            )
    return documents


def load_documents(directory: Path) -> list[Document]:
    """Carrega todos os documentos suportados de um diretório.

    Args:
        directory: Pasta com os arquivos de entrada.

    Returns:
        Lista de documentos, com o nome e o tipo do arquivo nos metadados.

    Raises:
        FileNotFoundError: Se o diretório não existir.
    """
    if not directory.is_dir():
        raise FileNotFoundError(f"Diretório de documentos não encontrado: {directory}")

    documents: list[Document] = []
    for path in sorted(directory.iterdir()):
        extension = path.suffix.lower()
        if extension in TEXT_EXTENSIONS:
            loaded = _load_text(path)
        elif extension in PDF_EXTENSIONS:
            loaded = _load_pdf(path)
        else:
            logger.warning("Arquivo ignorado, extensão não suportada: %s", path.name)
            continue

        for doc in loaded:
            doc.metadata["file_type"] = extension.lstrip(".")
        documents.extend(loaded)
        logger.info("Carregado %s: %d documento(s)", path.name, len(loaded))

    return documents
