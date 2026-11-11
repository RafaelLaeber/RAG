"""Tool de memória de longo prazo: o agente guarda fatos duráveis sobre o colaborador."""

import logging

from langchain.tools import ToolRuntime
from langchain_core.tools import tool
from langgraph.store.sqlite import SqliteStore

from agentic_rag.memory.store import UserContext, save_user_memory

logger = logging.getLogger(__name__)


@tool
def save_memory(content: str, runtime: ToolRuntime[UserContext]) -> str:
    """Guarda um fato duradouro sobre o colaborador para lembrar em conversas futuras.

    Use quando o colaborador informar algo útil para próximas conversas: nome, cargo,
    área, cidade, viagens planejadas, moeda que costuma usar ou preferências de resposta.
    Não guarde perguntas, valores pontuais nem trechos das políticas.

    Args:
        content: Fato curto e autocontido, em terceira pessoa (ex.: "Trabalha no time de vendas").
    """
    store = runtime.store
    if not isinstance(store, SqliteStore):
        return "Memória de longo prazo indisponível."
    save_user_memory(store, runtime.context.user_id, content)
    logger.info("Memória salva para %s: %s", runtime.context.user_id, content)
    return f"Memória salva: {content}"
