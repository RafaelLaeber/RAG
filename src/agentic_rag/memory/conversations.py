"""Histórico de conversas: cada usuário tem conversas e cada conversa guarda todas as mensagens.

Fica em SQLite, separado da memória de longo prazo (fatos) e do InMemorySaver (contexto do
agente na sessão). Serve para listar e reabrir conversas antigas.
"""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage

from agentic_rag.config import get_settings

TITLE_MAX_CHARS = 60

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations (user_id, updated_at DESC);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    tools TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages (conversation_id, id);
"""


@dataclass
class ConversationSummary:
    """Resumo de uma conversa para listar no histórico."""

    id: str
    title: str
    updated_at: datetime


@dataclass
class StoredMessage:
    """Mensagem persistida (role: "user" ou "assistant")."""

    role: str
    content: str
    tools: list[dict[str, Any]] = field(default_factory=list)


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    """Abre uma conexão curta (uma por operação, segura para uso em threads) e confirma ao sair."""
    path = get_settings().conversations_db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(str(path))) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(_SCHEMA)  # idempotente: cria as tabelas na primeira execução
        with conn:  # commit (ou rollback em caso de erro)
            yield conn


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _make_title(text: str) -> str:
    """Título da conversa: a primeira pergunta, em uma linha e truncada."""
    title = " ".join(text.split())
    return title if len(title) <= TITLE_MAX_CHARS else title[: TITLE_MAX_CHARS - 1] + "…"


def save_message(
    user_id: str,
    conversation_id: str,
    role: str,
    content: str,
    tools: list[dict[str, Any]] | None = None,
) -> None:
    """Grava uma mensagem, criando a conversa na primeira vez (título = primeira mensagem)."""
    now = _now()
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO conversations (id, user_id, title, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (conversation_id, user_id, _make_title(content), now, now),
        )
        conn.execute(
            "INSERT INTO messages (conversation_id, role, content, tools, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (conversation_id, role, content, json.dumps(tools or [], ensure_ascii=False), now),
        )
        conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conversation_id))


def list_conversations(user_id: str) -> list[ConversationSummary]:
    """Conversas do usuário, da mais recente para a mais antiga."""
    limit = get_settings().conversations_max_items
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, title, updated_at FROM conversations "
            "WHERE user_id = ? ORDER BY updated_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return [ConversationSummary(r[0], r[1], datetime.fromisoformat(r[2])) for r in rows]


def load_conversation(user_id: str, conversation_id: str) -> list[StoredMessage]:
    """Histórico completo de uma conversa (vazio se não existir ou for de outro usuário)."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT m.role, m.content, m.tools FROM messages m "
            "JOIN conversations c ON c.id = m.conversation_id "
            "WHERE c.id = ? AND c.user_id = ? ORDER BY m.id",
            (conversation_id, user_id),
        ).fetchall()
    return [StoredMessage(role, content, json.loads(tools)) for role, content, tools in rows]


def to_agent_messages(messages: list[StoredMessage]) -> list[AnyMessage]:
    """Converte o histórico salvo em mensagens do agente (só o texto, sem chamadas de tool).

    Usado para reabrir uma conversa antiga: o InMemorySaver não sobrevive ao processo,
    então o contexto é reconstruído a partir do SQLite.
    """
    return [HumanMessage(m.content) if m.role == "user" else AIMessage(m.content) for m in messages]
