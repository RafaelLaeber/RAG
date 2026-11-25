"""Middlewares de guardrail do agente.

- untrusted_tool_results: trata todo resultado de tool como dado não confiável. Fica no
  agente, e não dentro de cada tool, para nenhuma tool (inclusive as criadas depois)
  escapar do envelope por esquecimento.
- prompt_protection: responde pedidos diretos de prompt/instruções internas com a
  resposta fixa, antes de chamar o LLM (determinístico e sem custo).
"""

import logging
from collections.abc import Callable
from typing import Any

from langchain.agents.middleware import (
    AgentMiddleware,
    AgentState,
    ToolCallRequest,
    before_agent,
    wrap_tool_call,
)
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.runtime import Runtime
from langgraph.types import Command

from agentic_rag.guardrails.detection import find_injection_signals
from agentic_rag.guardrails.scope import CONFIDENTIAL_REPLY, is_prompt_extraction
from agentic_rag.guardrails.untrusted import wrap_untrusted

logger = logging.getLogger(__name__)


def _envelop_tool_result(
    request: ToolCallRequest,
    handler: Callable[[ToolCallRequest], ToolMessage | Command],
) -> ToolMessage | Command:
    """Executa a tool e envelopa o resultado como dado não confiável antes de ir ao LLM."""
    result = handler(request)
    if not isinstance(result, ToolMessage) or not isinstance(result.content, str):
        return result

    name = request.tool_call["name"]
    if signals := find_injection_signals(result.content):
        logger.warning("Possível prompt injection no resultado de %s: %s", name, signals)
    return result.model_copy(update={"content": wrap_untrusted(result.content, name)})


# Tipado como genérico para servir a qualquer agente (o decorator inferiria contexto None)
untrusted_tool_results: AgentMiddleware[Any, Any, Any] = wrap_tool_call(_envelop_tool_result)


PROMPT_PROTECTION_NODE = "PromptProtection.before_agent"  # nome do nó no grafo/stream


def _block_prompt_extraction(
    state: AgentState[Any], runtime: Runtime[Any]
) -> dict[str, Any] | None:
    """Responde com a mensagem fixa, sem chamar o LLM, se pedirem o prompt ou as instruções."""
    messages = state["messages"]
    last = messages[-1] if messages else None
    if not isinstance(last, HumanMessage) or not is_prompt_extraction(last.text):
        return None
    logger.warning("Pedido de prompt/instruções internas bloqueado: %r", last.text[:200])
    return {"messages": [AIMessage(CONFIDENTIAL_REPLY)], "jump_to": "end"}


prompt_protection: AgentMiddleware[Any, Any, Any] = before_agent(
    can_jump_to=["end"], name="PromptProtection"
)(_block_prompt_extraction)
