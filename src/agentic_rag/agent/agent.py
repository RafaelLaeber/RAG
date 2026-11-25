"""Factory do agente: LLM + tools (RAG, câmbio, memória) + memória de curto e longo prazo"""

from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import ModelRequest, SummarizationMiddleware, dynamic_prompt
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.sqlite import SqliteStore

from agentic_rag.agent.prompts import SUMMARY_PROMPT, SYSTEM_PROMPT, format_memories
from agentic_rag.config import get_settings
from agentic_rag.llm import get_chat_model
from agentic_rag.memory.store import UserContext, get_memory_store, load_user_memories
from agentic_rag.tools.api_tool import get_exchange_rate
from agentic_rag.tools.memory_tool import delete_memory, save_memory, update_memory
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
      Passando de `summary_trigger_messages` mensagens, as antigas viram um resumo
      e só as `summary_keep_messages` mais recentes seguem inteiras (economiza tokens).
    - Longo prazo: fatos sobre o colaborador no SQLite, separados por user_id
      (context=UserContext(user_id=...)). Persistem entre sessões. Vão no system prompt
      com seus ids, e o agente os mantém com save_memory, update_memory e delete_memory.

    Returns:
        Agente executável com invoke/stream.
    """
    settings = get_settings()
    model = get_chat_model()
    summarization: SummarizationMiddleware[Any, UserContext] = SummarizationMiddleware(
        model=model,
        trigger=("messages", settings.summary_trigger_messages),
        keep=("messages", settings.summary_keep_messages),
        summary_prompt=SUMMARY_PROMPT,
    )
    return create_agent(
        model=model,
        tools=[search_policies, get_exchange_rate, save_memory, update_memory, delete_memory],
        middleware=[summarization, _prompt_with_memories],
        context_schema=UserContext,
        checkpointer=InMemorySaver(),
        store=get_memory_store(),
        name="orbita_agent",  # nome do trace no LangSmith (padrão seria "LangGraph")
    )
