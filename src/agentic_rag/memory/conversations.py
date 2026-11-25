"""Histórico de conversas: cada usuário tem conversas e cada conversa guarda todas as mensagens.

Fica em SQLite, separado da memória de longo prazo (fatos) e dos checkpoints do agente
(contexto que o LLM vê). Serve para listar e reabrir conversas antigas.
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


def save_turn(
    user_id: str,
    conversation_id: str,
    question: str,
    answer: str,
    tools: list[dict[str, Any]] | None = None,
) -> None:
    """Grava a pergunta e a resposta de um turno numa única transação.

    Cria a conversa na primeira vez (título = primeira pergunta). Gravar as duas juntas
    garante que o histórico nunca fique com uma pergunta sem resposta.
    """
    now = _now()
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO conversations (id, user_id, title, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (conversation_id, user_id, _make_title(question), now, now),
        )
        conn.executemany(
            "INSERT INTO messages (conversation_id, role, content, tools, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (conversation_id, "user", question, "[]", now),
                (
                    conversation_id,
                    "assistant",
                    answer,
                    json.dumps(tools or [], ensure_ascii=False),
                    now,
                ),
            ],
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


def get_conversation(user_id: str, conversation_id: str) -> ConversationSummary | None:
    """Dados da conversa (None se não existir ou for de outro usuário)."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, title, updated_at FROM conversations WHERE id = ? AND user_id = ?",
            (conversation_id, user_id),
        ).fetchone()
    return ConversationSummary(row[0], row[1], datetime.fromisoformat(row[2])) if row else None


def conversation_owner(conversation_id: str) -> str | None:
    """Dono da conversa (None se ela ainda não existe). Serve para barrar ids de outro usuário."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT user_id FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
    return str(row[0]) if row else None


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


def delete_conversation(user_id: str, conversation_id: str) -> bool:
    """Apaga a conversa e suas mensagens (ON DELETE CASCADE), só se for do usuário.

    Retorna True se alguma conversa foi apagada.
    """
    with _connect() as conn:
        cursor = conn.execute(
            "DELETE FROM conversations WHERE id = ? AND user_id = ?", (conversation_id, user_id)
        )
    return cursor.rowcount > 0


def to_agent_messages(messages: list[StoredMessage]) -> list[AnyMessage]:
    """Converte o histórico salvo em mensagens do agente (só o texto, sem chamadas de tool).

    Usado para reabrir conversas sem checkpoint (ex.: gravadas antes do checkpointer em
    SQLite): o contexto do agente é reconstruído a partir do histórico.
    """
    return [HumanMessage(m.content) if m.role == "user" else AIMessage(m.content) for m in messages]
