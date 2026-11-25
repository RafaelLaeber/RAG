"""Base de conhecimento: listar, validar, enviar e indexar documentos (só administradores)."""

import logging
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from agentic_rag.api.deps import AdminUser
from agentic_rag.api.docs import errors
from agentic_rag.api.schemas import (
    ClearResultOut,
    DataFileOut,
    IngestionResultOut,
    UploadCheckOut,
    UploadErrorOut,
    UploadResultOut,
)
from agentic_rag.config import get_settings
from agentic_rag.ingestion.pipeline import clear_knowledge_base, delete_document, run_ingestion
from agentic_rag.ingestion.uploads import check_upload, save_upload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["documents"], responses=errors(401, 403))

Files = Annotated[
    list[UploadFile],
    File(description="Um ou mais arquivos `.md`, `.txt` ou `.pdf` (campo `files`)."),
]


def _ingest() -> IngestionResultOut:
    result = run_ingestion()
    return IngestionResultOut(total=result.total, added=result.added, deleted=result.deleted)


@router.get(
    "",
    summary="Listar documentos",
    response_description="Arquivos de `data/raw`, por nome.",
)
def list_files(_admin: AdminUser) -> list[DataFileOut]:
    """Arquivos da pasta `data/raw`, que é a fonte da base de conhecimento."""
    data_dir = get_settings().data_dir
    if not data_dir.exists():
        return []
    return [
        DataFileOut(name=p.name, size=p.stat().st_size)
        for p in sorted(data_dir.iterdir())
        if p.is_file() and not p.name.startswith(".")
    ]


@router.delete(
    "",
    summary="Apagar todos os documentos",
    response_description="Quantos arquivos foram apagados de `data/raw`.",
    responses=errors((502, "Não foi possível limpar a base (Astra DB indisponível).")),
)
def clear(_admin: AdminUser) -> ClearResultOut:
    """Apaga **todos** os arquivos de `data/raw` e todos os chunks da base vetorial.

    Sem volta: depois disso o agente não encontra nada nos documentos até que novos
    arquivos sejam enviados.
    """
    try:
        return ClearResultOut(removed=clear_knowledge_base())
    except Exception:
        logger.exception("Falha ao apagar a base de conhecimento")
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Não foi possível apagar a base. Verifique o Astra DB e tente de novo.",
        ) from None


@router.delete(
    "/{name}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Apagar um documento",
    responses=errors(
        (404, "Não existe arquivo com esse nome em `data/raw`."),
        (502, "Não foi possível limpar a base (Astra DB indisponível)."),
    ),
)
def delete_one(name: str, _admin: AdminUser) -> None:
    """Apaga um arquivo de `data/raw` e os chunks dele na base vetorial."""
    try:
        found = delete_document(name)
    except Exception:
        logger.exception("Falha ao apagar o documento %s", name)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Não foi possível apagar o documento. Verifique o Astra DB e tente de novo.",
        ) from None
    if not found:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento não encontrado.")


@router.post(
    "/check",
    summary="Validar arquivos (sem gravar)",
    response_description="Uma validação por arquivo, na ordem enviada.",
)
def check(files: Files, _admin: AdminUser) -> list[UploadCheckOut]:
    """Valida os arquivos **sem salvar nada**, para a interface mostrar o status antes do envio.

    Um arquivo é recusado (`ok: false`, motivo em `error`) se tiver extensão fora de `.md`,
    `.txt` e `.pdf`, passar de `UPLOAD_MAX_MB`, não estiver em UTF-8, tiver front matter
    inválido ou for um PDF sem texto. Texto com cara de instrução ao agente só gera alerta
    (`injection_signals`).
    """
    results = []
    for file in files:
        c = check_upload(file.filename or "", file.file.read())
        results.append(
            UploadCheckOut(
                name=c.name,
                size=c.size,
                ok=c.ok,
                error=c.error,
                injection_signals=c.injection_signals,
                replaces=c.replaces,
            )
        )
    return results


@router.post(
    "",
    summary="Enviar arquivos e indexar",
    response_description="Arquivos salvos, recusados e resultado da indexação.",
)
def upload(files: Files, _admin: AdminUser) -> UploadResultOut:
    """Salva em `data/raw` os arquivos válidos (as mesmas regras de `/check`) e reindexa a base.

    Os inválidos voltam em `errors`, sem derrubar a requisição. Um arquivo com o mesmo nome
    de um existente o substitui. Se a indexação falhar, os arquivos continuam salvos e a
    mensagem vem em `ingestion_error`: tente de novo em `POST /api/documents/ingest`.
    """
    saved: list[str] = []
    upload_errors: list[UploadErrorOut] = []
    for file in files:
        data = file.file.read()
        c = check_upload(file.filename or "", data)
        if not c.ok:
            upload_errors.append(UploadErrorOut(name=c.name, message=c.error or "arquivo inválido"))
            continue
        try:
            save_upload(c.name, data)
        except (ValueError, OSError) as exc:
            logger.exception("Falha ao salvar %s", c.name)
            upload_errors.append(
                UploadErrorOut(name=c.name, message=f"Não foi possível salvar: {exc}")
            )
            continue
        saved.append(c.name)

    ingestion: IngestionResultOut | None = None
    ingestion_error: str | None = None
    if saved:
        try:
            ingestion = _ingest()
        except Exception:  # noqa: BLE001 - os arquivos já estão salvos; só avisa da indexação
            logger.exception("Falha na ingestão após o upload")
            ingestion_error = (
                "Os arquivos foram salvos, mas a indexação falhou. "
                "Tente de novo em Gerar embeddings."
            )
    return UploadResultOut(
        saved=saved, errors=upload_errors, ingestion=ingestion, ingestion_error=ingestion_error
    )


@router.post(
    "/ingest",
    summary="Gerar embeddings (reindexar)",
    response_description="Chunks na base, adicionados e removidos.",
    responses=errors((502, "A ingestão falhou (Astra DB ou OpenAI indisponível).")),
)
def ingest(_admin: AdminUser) -> IngestionResultOut:
    """Sincroniza a base vetorial (Astra DB) com `data/raw`.

    Só os chunks novos ou alterados geram embedding, e os de documentos editados ou
    removidos são apagados. Sem mudanças, nada é alterado. **Tudo na collection que não
    vier de `data/raw` é removido.**
    """
    try:
        return _ingest()
    except Exception:
        logger.exception("Falha na ingestão")
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Falha na ingestão. Verifique o Astra DB e a OpenAI e tente de novo.",
        ) from None
