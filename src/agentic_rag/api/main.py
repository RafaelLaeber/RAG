"""App FastAPI do assistente.

Uso: uvicorn agentic_rag.api.main:app --reload
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse

from agentic_rag.agent.agent import get_agent
from agentic_rag.api.deps import CurrentUser
from agentic_rag.api.docs import DESCRIPTION, TAGS, errors
from agentic_rag.api.routers import auth, chat, conversations, documents, users
from agentic_rag.api.schemas import MetaOut
from agentic_rag.config import get_settings, setup_langsmith
from agentic_rag.ingestion.uploads import SUPPORTED_EXTENSIONS

FRONTEND_DIST = Path("frontend/dist")

status_router = APIRouter(prefix="/api", tags=["status"])


@status_router.get("/health", summary="Saúde da API", response_description="A API está no ar.")
def health() -> dict[str, str]:
    """Responde `{"status": "ok"}` se a API está no ar. Não exige login e não consulta
    o banco, a OpenAI nem o Astra."""
    return {"status": "ok"}


@status_router.get(
    "/meta",
    summary="Configurações públicas",
    response_description="Modelo, LangSmith e limites de upload.",
    responses=errors(401),
)
def meta(_user: CurrentUser) -> MetaOut:
    """Configurações que a interface mostra ou usa: o modelo do agente, se o LangSmith está
    ligado e os limites de upload. Nenhum segredo sai daqui."""
    settings = get_settings()
    return MetaOut(
        llm_model=settings.llm_model,
        langsmith=setup_langsmith(),
        upload_max_mb=settings.upload_max_mb,
        supported_extensions=sorted(SUPPORTED_EXTENSIONS),
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Liga o LangSmith e cria o agente uma vez por processo (reaproveita as conexões SQLite)."""
    setup_langsmith()
    app.state.agent = get_agent()
    yield


def _mount_frontend(app: FastAPI, dist: Path) -> None:
    """Serve o build do React na raiz, com fallback para o index.html (SPA)."""
    index = dist / "index.html"
    root = dist.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404, "Rota não encontrada.")
        candidate = (root / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        return FileResponse(index)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Assistente Vega",
        version="2.0.1",
        description=DESCRIPTION,
        openapi_tags=TAGS,
        swagger_ui_parameters={"defaultModelsExpandDepth": 0},  # esconde os schemas no fim
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    app.include_router(status_router)
    app.include_router(auth.router)
    app.include_router(conversations.router)
    app.include_router(chat.router)
    app.include_router(documents.router)
    app.include_router(users.router)
    if (FRONTEND_DIST / "index.html").is_file():
        _mount_frontend(app, FRONTEND_DIST)
    return app


app = create_app()
