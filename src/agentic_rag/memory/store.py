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


def save_user_memory(store: SqliteStore, user_id: str, content: str) -> None:
    """Grava um fato sobre o usuário."""
    store.put(_namespace(user_id), str(uuid.uuid4()), {"content": content})


def load_user_memories(store: SqliteStore, user_id: str) -> list[str]:
    """Lista os fatos guardados do usuário (mais antigos primeiro)."""
    limit = get_settings().memory_max_items
    items = store.search(_namespace(user_id), limit=limit)
    items.sort(key=lambda item: item.created_at)
    return [item.value["content"] for item in items]
