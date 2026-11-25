"""Tools de memória de longo prazo: o agente guarda, corrige e apaga fatos sobre o colaborador."""

import logging

from langchain.tools import ToolRuntime
from langchain_core.tools import tool
from langgraph.store.sqlite import SqliteStore

from agentic_rag.memory.store import (
    UserContext,
    delete_user_memory,
    save_user_memory,
    update_user_memory,
)

logger = logging.getLogger(__name__)

_UNAVAILABLE = "Memória de longo prazo indisponível."


def _not_found(memory_id: str) -> str:
    return f"Memória não encontrada: {memory_id}. Use um id da lista de memórias."


@tool
def save_memory(content: str, runtime: ToolRuntime[UserContext]) -> str:
    """Guarda um fato duradouro e novo sobre o colaborador para lembrar em conversas futuras.

    Use quando o colaborador informar algo útil para próximas conversas: nome, cargo,
    área, cidade, viagens planejadas, moeda que costuma usar ou preferências de resposta.
    Não guarde perguntas, valores pontuais nem trechos das políticas. Se já existir um
    fato equivalente na memória, não salve de novo; se ele mudou, use update_memory.

    Args:
        content: Fato curto e autocontido, em terceira pessoa (ex.: "Trabalha no time de vendas").
    """
    store = runtime.store
    if not isinstance(store, SqliteStore):
        return _UNAVAILABLE
    memory_id = save_user_memory(store, runtime.context.user_id, content)
    logger.info("Memória %s salva para %s: %s", memory_id, runtime.context.user_id, content)
    return f"Memória salva: {content}"


@tool
def update_memory(memory_id: str, content: str, runtime: ToolRuntime[UserContext]) -> str:
    """Corrige um fato já guardado sobre o colaborador, substituindo o texto antigo.

    Use quando um fato da memória mudou ou ficou incompleto (ex.: o colaborador mudou de
    cidade ou de cargo), em vez de salvar um fato novo com save_memory.

    Args:
        memory_id: Id do fato, exatamente como aparece entre colchetes na memória.
        content: Novo texto completo do fato, curto e em terceira pessoa.
    """
    store = runtime.store
    if not isinstance(store, SqliteStore):
        return _UNAVAILABLE
    user_id = runtime.context.user_id
    if not update_user_memory(store, user_id, memory_id, content):
        logger.warning("Memória %s não encontrada para %s (update)", memory_id, user_id)
        return _not_found(memory_id)
    logger.info("Memória %s atualizada para %s: %s", memory_id, user_id, content)
    return f"Memória atualizada: {content}"


@tool
def delete_memory(memory_id: str, runtime: ToolRuntime[UserContext]) -> str:
    """Apaga um fato guardado sobre o colaborador.

    Use para remover fatos duplicados (mantendo um só), fatos errados ou que deixaram de
    valer, ou quando o colaborador pedir para esquecer algo.

    Args:
        memory_id: Id do fato, exatamente como aparece entre colchetes na memória.
    """
    store = runtime.store
    if not isinstance(store, SqliteStore):
        return _UNAVAILABLE
    user_id = runtime.context.user_id
    if not delete_user_memory(store, user_id, memory_id):
        logger.warning("Memória %s não encontrada para %s (delete)", memory_id, user_id)
        return _not_found(memory_id)
    logger.info("Memória %s apagada para %s", memory_id, user_id)
    return "Memória apagada."
