"""Factory do agente: LLM + tools (RAG, câmbio, memória) + memória de curto e longo prazo"""

from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import ModelRequest, dynamic_prompt
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.sqlite import SqliteStore

from agentic_rag.agent.prompts import SYSTEM_PROMPT, format_memories
from agentic_rag.llm import get_chat_model
from agentic_rag.memory.store import UserContext, get_memory_store, load_user_memories
from agentic_rag.tools.api_tool import get_exchange_rate
from agentic_rag.tools.memory_tool import save_memory
from agentic_rag.tools.rag_tool import search_policies


@dynamic_prompt
def _prompt_with_memories(request: ModelRequest[UserContext]) -> str:
    """Monta o system prompt com as memórias de longo prazo do colaborador."""
    store = request.runtime.store
    context = request.runtime.context
    if not isinstance(store, SqliteStore) or not isinstance(context, UserContext):
        return SYSTEM_PROMPT
    return SYSTEM_PROMPT + format_memories(load_user_memories(store, context.user_id))


def get_agent() -> CompiledStateGraph[Any, UserContext, Any, Any]:
    """Cria o agente ReAct com tool calling e memória híbrida.

    - Curto prazo: histórico da conversa no checkpointer, separado por thread_id
      (config={"configurable": {"thread_id": ...}}). Some ao fechar o processo.
    - Longo prazo: fatos sobre o colaborador no SQLite, separados por user_id
      (context=UserContext(user_id=...)). Persistem entre sessões.

    Returns:
        Agente executável com invoke/stream.
    """
    return create_agent(
        model=get_chat_model(),
        tools=[search_policies, get_exchange_rate, save_memory],
        middleware=[_prompt_with_memories],
        context_schema=UserContext,
        checkpointer=InMemorySaver(),
        store=get_memory_store(),
        name="orbita_agent",  # nome do trace no LangSmith (padrão seria "LangGraph")
    )
