"""Lógica de um turno de conversa com o agente, sem dependência de framework web.

`run_turn` é um gerador síncrono de eventos tipados: a API os converte em SSE, mas nada
aqui conhece HTTP.
"""

import logging
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from typing import Any, ClassVar, cast

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import StateSnapshot

from agentic_rag.agent.agent import Agent, rollback_turn
from agentic_rag.config import get_settings
from agentic_rag.guardrails.middleware import PROMPT_PROTECTION_NODE
from agentic_rag.memory.conversations import (
    load_conversation,
    save_turn,
    to_agent_messages,
)
from agentic_rag.memory.store import UserContext

logger = logging.getLogger(__name__)

ERROR_ANSWER = (
    "Não consegui responder agora por uma falha interna. Tente de novo em instantes; "
    "se o problema continuar, avise o time responsável pelo assistente."
)


@dataclass
class ChatEvent:
    """Evento de um turno. `name` é o tipo; os campos viram o `data` do evento."""

    name: ClassVar[str]

    def data(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ConversationEvent(ChatEvent):
    name: ClassVar[str] = "conversation"
    id: str


@dataclass
class TokenEvent(ChatEvent):
    name: ClassVar[str] = "token"
    text: str


@dataclass
class ResetEvent(ChatEvent):
    name: ClassVar[str] = "reset"


@dataclass
class ToolEvent(ChatEvent):
    name: ClassVar[str] = "tool"
    # "tool_name" evita colidir com o ClassVar `name`; o JSON usa "name" (ver data())
    tool_name: str
    args: dict[str, Any] = field(default_factory=dict)

    def data(self) -> dict[str, Any]:
        return {"name": self.tool_name, "args": self.args}


@dataclass
class AnswerEvent(ChatEvent):
    name: ClassVar[str] = "answer"
    content: str
    tools: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ErrorEvent(ChatEvent):
    name: ClassVar[str] = "error"
    message: str


@dataclass
class DoneEvent(ChatEvent):
    name: ClassVar[str] = "done"


def _rollback(agent: Agent, config: RunnableConfig, before: StateSnapshot | None) -> None:
    if before is None:  # falhou antes de ler o estado: nada a desfazer
        return
    try:
        rollback_turn(agent, config, before)
    except Exception:  # noqa: BLE001 - o turno já falhou; só registra
        thread_id = config["configurable"]["thread_id"]
        logger.exception("Falha ao desfazer o turno (thread %s)", thread_id)


def run_turn(
    agent: Agent, user_id: str, conversation_id: str, question: str
) -> Iterator[ChatEvent]:
    """Executa um turno do agente em streaming.

    Em sucesso, grava pergunta e resposta juntas no histórico (antes do `AnswerEvent`).
    Em falha, desfaz o checkpoint e emite `ErrorEvent`: o turno não entra no histórico.
    Sempre começa com `ConversationEvent` e termina com `DoneEvent`.
    """
    settings = get_settings()
    context = UserContext(user_id=user_id)
    config: RunnableConfig = {
        "configurable": {"thread_id": conversation_id},
        "metadata": {
            "thread_id": conversation_id,
            "user_id": user_id,
            "llm_model": settings.llm_model,
        },
        "tags": ["api", "memoria-sqlite"],
    }
    yield ConversationEvent(conversation_id)

    tools: list[dict[str, Any]] = []
    answer = ""
    before: StateSnapshot | None = None
    try:
        # Estado antes do turno: usado para desfazê-lo se falhar no meio
        before = agent.get_state(config)

        # Conversa sem checkpoint (ex.: gravada antes do checkpointer em SQLite): reconstrói
        # o contexto a partir do histórico salvo
        history = (
            [] if before.values else to_agent_messages(load_conversation(user_id, conversation_id))
        )

        # "messages" entrega os tokens do LLM conforme são gerados; "updates" entrega cada
        # passo completo (chamadas de tool e a resposta final)
        stream = cast(
            Iterator[tuple[str, Any]],
            agent.stream(
                {"messages": [*history, HumanMessage(question)]},
                config,
                context=context,
                stream_mode=["messages", "updates"],
            ),
        )
        for mode, data in stream:
            if mode == "messages":
                chunk, meta = data
                # Só tokens do nó "model": o resumo (SummarizationMiddleware) também chama o
                # LLM, e o texto dele não é a resposta ao colaborador
                if (
                    meta.get("langgraph_node") == "model"
                    and isinstance(chunk, AIMessageChunk)
                    and (text := chunk.text)
                ):
                    yield TokenEvent(text)
                continue

            for node, step in data.items():
                # Só o nó "model" (LLM) e o guardrail de prompt (resposta fixa, sem LLM) trazem
                # mensagens novas. O resumo devolve as antigas preservadas, que apareceriam
                # de novo como se fossem deste turno.
                if node not in ("model", PROMPT_PROTECTION_NODE) or not isinstance(step, dict):
                    continue
                for message in step.get("messages", []):
                    if isinstance(message, AIMessage) and message.tool_calls:
                        # Texto que veio antes de uma chamada de tool não é a resposta
                        yield ResetEvent()
                        for call in message.tool_calls:
                            call_args = dict(call["args"])
                            tools.append({"name": call["name"], "args": call_args})
                            yield ToolEvent(call["name"], call_args)
                    elif isinstance(message, ToolMessage):
                        continue
                    elif isinstance(message, AIMessage):
                        answer = message.text
        save_turn(user_id, conversation_id, question, answer, tools)
    except GeneratorExit:
        # O cliente desconectou no meio do turno: desfaz para não deixar o checkpoint pela metade
        logger.warning("Cliente desconectou no meio do turno (thread %s)", conversation_id)
        _rollback(agent, config, before)
        raise
    except Exception:  # noqa: BLE001 - qualquer falha vira mensagem amigável ao usuário
        # Detalhes técnicos só no log (e no trace do LangSmith), não para o cliente
        logger.exception("Falha ao executar o agente (thread %s)", conversation_id)
        _rollback(agent, config, before)
        yield ErrorEvent(ERROR_ANSWER)
    else:
        yield AnswerEvent(answer, tools)
    yield DoneEvent()
