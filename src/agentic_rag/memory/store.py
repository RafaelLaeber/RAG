"""Memória de longo prazo: fatos sobre o colaborador guardados em SQLite, entre sessões."""

import logging
import sqlite3
import uuid
from dataclasses import dataclass
from functools import lru_cache

from langgraph.store.base import Item
from langgraph.store.sqlite import SqliteStore

from agentic_rag.config import get_settings

logger = logging.getLogger(__name__)

_PAGE_SIZE = 100  # itens por página ao ler o namespace inteiro


class MemoryFullError(Exception):
    """O colaborador já tem o máximo de fatos; é preciso atualizar ou apagar algum."""


@dataclass
class UserContext:
    """Contexto de execução do agente (passado em context= no invoke/stream)."""

    user_id: str


def _namespace(user_id: str) -> tuple[str, str]:
    """Namespace das memórias de um usuário no store."""
    return ("memories", user_id)


@lru_cache  # Uma conexão por processo
def get_memory_store() -> SqliteStore:
    """Abre (ou cria) o banco SQLite das memórias de longo prazo.

    Returns:
        Store do LangGraph persistido no arquivo de `memory_db_path`.
    """
    path = get_settings().memory_db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    # Mesmos parâmetros do SqliteStore.from_conn_string, sem o context manager
    conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
    store = SqliteStore(conn)
    store.setup()  # cria as tabelas na primeira execução
    return store


@dataclass(frozen=True)
class Memory:
    """Fato guardado sobre o usuário, com o id usado para atualizá-lo ou apagá-lo."""

    id: str
    content: str


def _all_items(store: SqliteStore, user_id: str) -> list[Item]:
    """Todos os fatos do usuário (o search do store pagina e tem limite padrão de 10)."""
    items: list[Item] = []
    while True:
        page = store.search(_namespace(user_id), limit=_PAGE_SIZE, offset=len(items))
        items.extend(page)
        if len(page) < _PAGE_SIZE:
            return items


def save_user_memory(store: SqliteStore, user_id: str, content: str) -> str:
    """Grava um fato sobre o usuário e devolve o id gerado.

    Raises:
        MemoryFullError: Se o usuário já tiver `memory_max_items` fatos. Recusar na
            gravação evita que fatos passem do limite e sumam do prompt sem aviso.
    """
    limit = get_settings().memory_max_items
    if len(_all_items(store, user_id)) >= limit:
        raise MemoryFullError(f"Memória cheia ({limit} fatos)")
    memory_id = str(uuid.uuid4())
    store.put(_namespace(user_id), memory_id, {"content": content})
    return memory_id


def load_user_memories(store: SqliteStore, user_id: str) -> list[Memory]:
    """Lista os fatos do usuário (mais antigos primeiro), até `memory_max_items`.

    Com o limite aplicado na gravação, o corte só acontece em bancos antigos ou se o
    limite for reduzido. Nesse caso ficam os fatos atualizados mais recentemente,
    escolhidos aqui de forma explícita, sem depender da ordem devolvida pelo store.
    (O SqliteStore grava os horários com resolução de segundos; empates ficam na ordem
    do store.)
    """
    limit = get_settings().memory_max_items
    items = _all_items(store, user_id)
    if len(items) > limit:
        logger.warning(
            "%s tem %d memórias; só as %d mais recentes vão para o prompt",
            user_id,
            len(items),
            limit,
        )
    items.sort(key=lambda item: item.updated_at, reverse=True)
    kept = sorted(items[:limit], key=lambda item: item.created_at)
    return [Memory(id=item.key, content=item.value["content"]) for item in kept]


def _exists(store: SqliteStore, user_id: str, memory_id: str) -> bool:
    """Diz se o id existe no namespace do usuário (memória de outro usuário não conta)."""
    return store.get(_namespace(user_id), memory_id) is not None


def update_user_memory(store: SqliteStore, user_id: str, memory_id: str, content: str) -> bool:
    """Substitui o conteúdo de um fato do usuário.

    Returns:
        False se o id não existir entre as memórias desse usuário.
    """
    if not _exists(store, user_id, memory_id):
        return False
    store.put(_namespace(user_id), memory_id, {"content": content})
    return True


def delete_user_memory(store: SqliteStore, user_id: str, memory_id: str) -> bool:
    """Apaga um fato do usuário.

    Returns:
        False se o id não existir entre as memórias desse usuário.
    """
    if not _exists(store, user_id, memory_id):
        return False
    store.delete(_namespace(user_id), memory_id)
    return True
