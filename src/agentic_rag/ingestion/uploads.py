"""Upload de documentos novos para a pasta de entrada (data/raw).

O arquivo é validado antes de ser gravado, com as mesmas regras dos loaders: extensão
suportada, texto em UTF-8, front matter válido e PDF com texto extraível. Assim um
arquivo quebrado não derruba a ingestão de todos os outros.
"""

import io
import logging
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from agentic_rag.config import get_settings
from agentic_rag.guardrails.detection import find_injection_signals
from agentic_rag.ingestion.loaders import PDF_EXTENSIONS, TEXT_EXTENSIONS, split_front_matter

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | PDF_EXTENSIONS


@dataclass
class UploadCheck:
    """Resultado da validação de um arquivo enviado."""

    name: str  # nome final na pasta (sem diretórios)
    size: int  # bytes
    error: str | None = None  # motivo da recusa; None = pode enviar
    injection_signals: list[str] = field(default_factory=list)  # só alerta, não bloqueia
    replaces: bool = False  # já existe um arquivo com esse nome em data_dir

    @property
    def ok(self) -> bool:
        return self.error is None


def safe_filename(name: str) -> str:
    """Nome do arquivo sem diretórios (evita gravar fora de data_dir, ex.: '../x.md')."""
    return Path(name.replace("\\", "/")).name.strip()


def _extract_text(name: str, data: bytes) -> str:
    """Texto do arquivo, do mesmo jeito que os loaders vão ler. Levanta ValueError se inválido."""
    if Path(name).suffix.lower() in PDF_EXTENSIONS:
        try:
            reader = PdfReader(io.BytesIO(data))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except (PdfReadError, OSError, ValueError) as exc:
            raise ValueError(f"PDF inválido ou corrompido ({exc})") from exc
        if not text.strip():
            raise ValueError("PDF sem texto extraível (pode ser imagem escaneada)")
        return text

    try:
        content = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("o arquivo precisa estar em UTF-8") from exc
    try:
        _, body = split_front_matter(content)
    except Exception as exc:  # noqa: BLE001 - YAML inválido tem vários tipos de erro
        first_line = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
        raise ValueError(f"front matter inválido ({first_line})") from exc
    if not body.strip():
        raise ValueError("arquivo sem texto")
    return body


def check_upload(name: str, data: bytes) -> UploadCheck:
    """Valida um arquivo antes de gravá-lo em data_dir."""
    settings = get_settings()
    filename = safe_filename(name)
    check = UploadCheck(
        name=filename,
        size=len(data),
        replaces=bool(filename) and (settings.data_dir / filename).is_file(),
    )

    extension = Path(filename).suffix.lower()
    max_bytes = settings.upload_max_mb * 1024 * 1024
    if not filename or filename.startswith("."):
        check.error = "nome de arquivo inválido"
    elif extension not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        check.error = f"extensão não suportada (use {supported})"
    elif len(data) > max_bytes:
        check.error = f"arquivo maior que {settings.upload_max_mb} MB"
    else:
        try:
            check.injection_signals = find_injection_signals(_extract_text(filename, data))
        except ValueError as exc:
            check.error = str(exc)
    return check


def save_upload(name: str, data: bytes) -> Path:
    """Grava o arquivo em data_dir (substitui se já existir).

    Grava num arquivo temporário e renomeia no fim, para a ingestão nunca ler um
    arquivo pela metade.

    Raises:
        ValueError: Se o arquivo não passar em check_upload.
    """
    check = check_upload(name, data)
    if not check.ok:
        raise ValueError(f"{check.name}: {check.error}")

    data_dir = get_settings().data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    target = data_dir / check.name
    temporary = target.with_name(f".{check.name}.tmp")
    temporary.write_bytes(data)
    temporary.replace(target)
    logger.info("Arquivo salvo em %s (%d bytes)", target, check.size)
    return target
