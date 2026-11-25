"""Memória de longo prazo: fatos sobre o colaborador guardados em SQLite, entre sessões."""

import sqlite3
import uuid
from dataclasses import dataclass
from functools import lru_cache

from langgraph.store.sqlite import SqliteStore

from agentic_rag.config import get_settings


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


def save_user_memory(store: SqliteStore, user_id: str, content: str) -> str:
    """Grava um fato sobre o usuário e devolve o id gerado."""
    memory_id = str(uuid.uuid4())
    store.put(_namespace(user_id), memory_id, {"content": content})
    return memory_id


def load_user_memories(store: SqliteStore, user_id: str) -> list[Memory]:
    """Lista os fatos guardados do usuário (mais antigos primeiro)."""
    limit = get_settings().memory_max_items
    items = store.search(_namespace(user_id), limit=limit)
    items.sort(key=lambda item: item.created_at)
    return [Memory(id=item.key, content=item.value["content"]) for item in items]


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
