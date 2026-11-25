"""Pipeline de ingestão: carregar, dividir e sincronizar os documentos com o vector store."""

import hashlib
import json
import logging
from dataclasses import asdict, dataclass

from langchain_astradb import AstraDBVectorStore
from langchain_core.documents import Document
from langsmith import traceable

from agentic_rag.config import get_settings, setup_langsmith
from agentic_rag.guardrails.detection import find_injection_signals
from agentic_rag.ingestion.loaders import load_documents
from agentic_rag.ingestion.splitter import split_documents
from agentic_rag.ingestion.tracing import summarize_documents
from agentic_rag.ingestion.uploads import safe_filename
from agentic_rag.retrieval.vectorstore import get_vector_store

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestionResult:
    """Resultado da sincronização com o vector store."""

    total: int  # chunks na base após a ingestão
    added: int  # chunks novos ou alterados (embeddings gerados)
    deleted: int  # chunks antigos removidos (documento editado ou apagado)


def _chunk_id(chunk: Document) -> str:
    """ID estável do chunk: muda se o texto ou qualquer metadado mudar.

    Os metadados entram no hash para que mudar só o front matter (ex.: status de
    "vigente" para "substituida") também gere um chunk novo e apague o antigo.
    """
    metadata = json.dumps(chunk.metadata, sort_keys=True, ensure_ascii=False, default=str)
    key = f"{metadata}|{chunk.page_content}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _existing_ids(vector_store: AstraDBVectorStore) -> set[str]:
    """IDs de todos os chunks hoje na collection (só o _id, sem texto nem vetor)."""
    vector_store.astra_env.ensure_db_setup()
    cursor = vector_store.astra_env.collection.find({}, projection={"_id": True})
    return {str(doc["_id"]) for doc in cursor}


@traceable(
    run_type="chain",
    name="sync_chunks",
    process_inputs=lambda inputs: {"chunks": summarize_documents(inputs["chunks"])},
    process_outputs=asdict,
)
def _sync_chunks(chunks: list[Document]) -> IngestionResult:
    """Deixa a collection igual aos chunks atuais; os embeddings aparecem como runs filhos.

    Primeiro grava os chunks novos e só depois apaga os antigos, para a base nunca
    ficar vazia no meio da ingestão. Chunks que não mudaram não geram embedding de novo.
    """
    by_id = {_chunk_id(chunk): chunk for chunk in chunks}  # chunks idênticos viram um só
    vector_store = get_vector_store()
    existing = _existing_ids(vector_store)

    new_ids = [chunk_id for chunk_id in by_id if chunk_id not in existing]
    if new_ids:
        vector_store.add_documents([by_id[chunk_id] for chunk_id in new_ids], ids=new_ids)

    stale_ids = existing - by_id.keys()
    if stale_ids:
        vector_store.delete(ids=list(stale_ids))

    return IngestionResult(total=len(by_id), added=len(new_ids), deleted=len(stale_ids))


@traceable(run_type="chain", name="ingestion", tags=["ingestion"], process_outputs=asdict)
def run_ingestion() -> IngestionResult:
    """Sincroniza a collection com os documentos de `data_dir`.

    A pasta é a fonte da verdade: chunks de documentos editados ou removidos são
    apagados da collection, e rodar de novo sem mudanças não altera nada.

    Returns:
        Quantos chunks a base tem e quantos foram adicionados e removidos.

    Raises:
        ValueError: Se nenhum chunk for gerado (evita esvaziar a base por engano).
    """
    settings = get_settings()

    documents = load_documents(settings.data_dir)
    for doc in documents:
        # Só alerta: o documento é indexado mesmo assim e, na consulta, chega ao agente
        # envelopado como dado não confiável (guardrails/middleware.py)
        if signals := find_injection_signals(doc.page_content):
            logger.warning(
                "Possível instrução embutida em %s (página %s): %s",
                doc.metadata.get("source"),
                doc.metadata.get("page", "-"),
                signals,
            )
    chunks = split_documents(documents, settings.chunk_size, settings.chunk_overlap)
    if not chunks:
        raise ValueError(f"Nenhum documento com texto em {settings.data_dir}; base mantida.")

    for chunk in chunks:
        chunk.metadata["embedding_model"] = settings.embedding_model

    result = _sync_chunks(chunks)
    logger.info(
        "Ingestão concluída: %d chunk(s) na base, %d adicionado(s), %d removido(s)",
        result.total,
        result.added,
        result.deleted,
    )
    return result


def clear_knowledge_base() -> int:
    """Apaga todos os chunks da collection e todos os arquivos de `data_dir`.

    O índice é limpo primeiro: se o Astra falhar, nada foi apagado. Se a remoção de um
    arquivo falhar depois, o erro sobe e a pasta pode ficar com arquivos já sem índice
    (rodar a ingestão resolve).

    Returns:
        Quantos arquivos foram removidos de `data_dir`.
    """
    settings = get_settings()
    vector_store = get_vector_store()
    ids = list(_existing_ids(vector_store))
    if ids:
        vector_store.delete(ids=ids)

    removed = 0
    if settings.data_dir.exists():
        for path in settings.data_dir.iterdir():
            if path.is_file() and not path.name.startswith("."):
                path.unlink()
                removed += 1
    logger.info("Base limpa: %d chunk(s) e %d arquivo(s) removido(s)", len(ids), removed)
    return removed


def delete_document(name: str) -> bool:
    """Apaga um arquivo de `data_dir` e os chunks dele no Astra (índice primeiro).

    Returns:
        `False` se não existir um arquivo com esse nome em `data_dir`.
    """
    path = get_settings().data_dir / safe_filename(name)
    if not path.is_file() or path.name.startswith("."):
        return False
    get_vector_store().delete_by_metadata_filter({"source": path.name})
    path.unlink()
    logger.info("Documento removido: %s", path.name)
    return True


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    setup_langsmith()
    run_ingestion()
