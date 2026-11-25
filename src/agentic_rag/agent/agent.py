"""Factory do agente: LLM + tools (RAG, câmbio, memória) + memória de curto e longo prazo"""

import sqlite3
from functools import lru_cache
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import ModelRequest, SummarizationMiddleware, dynamic_prompt
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.sqlite import SqliteStore
from langgraph.types import StateSnapshot

from agentic_rag.agent.prompts import SUMMARY_PROMPT, SYSTEM_PROMPT, format_memories
from agentic_rag.config import get_settings
from agentic_rag.guardrails.middleware import prompt_protection, untrusted_tool_results
from agentic_rag.llm import get_chat_model
from agentic_rag.memory.store import UserContext, get_memory_store, load_user_memories
from agentic_rag.tools.api_tool import convert_currency, get_exchange_rate
from agentic_rag.tools.memory_tool import delete_memory, save_memory, update_memory
from agentic_rag.tools.rag_tool import search_policies

Agent = CompiledStateGraph[Any, UserContext, Any, Any]


@dynamic_prompt
def _prompt_with_memories(request: ModelRequest[UserContext]) -> str:
    """Monta o system prompt com as memórias de longo prazo do colaborador."""
    store = request.runtime.store
    context = request.runtime.context
    if not isinstance(store, SqliteStore) or not isinstance(context, UserContext):
        return SYSTEM_PROMPT
    return SYSTEM_PROMPT + format_memories(load_user_memories(store, context.user_id))


@lru_cache  # Uma conexão por processo (o SqliteSaver serializa o acesso com um lock)
def get_checkpointer() -> SqliteSaver:
    """Abre (ou cria) o banco SQLite com os checkpoints das conversas."""
    path = get_settings().checkpoints_db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    saver = SqliteSaver(sqlite3.connect(str(path), check_same_thread=False))
    saver.setup()  # cria as tabelas na primeira execução
    return saver


def get_agent() -> Agent:
    """Cria o agente ReAct com tool calling e memória híbrida.

    - Curto prazo: estado da conversa (mensagens, chamadas de tool e resumo) em checkpoints
      no SQLite, separados por thread_id (config={"configurable": {"thread_id": ...}}).
      Sobrevive a reinícios. Passando de `summary_trigger_tokens` tokens, as mensagens
      antigas viram um resumo e só as mais recentes (cerca de `summary_keep_tokens`)
      seguem inteiras.
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
        trigger=("tokens", settings.summary_trigger_tokens),
        keep=("tokens", settings.summary_keep_tokens),
        summary_prompt=SUMMARY_PROMPT,
    )
    return create_agent(
        model=model,
        tools=[
            search_policies,
            get_exchange_rate,
            convert_currency,
            save_memory,
            update_memory,
            delete_memory,
        ],
        # prompt_protection responde pedidos de prompt/instruções sem chamar o LLM;
        # untrusted_tool_results envelopa todo resultado de tool como dado não confiável
        middleware=[
            prompt_protection,
            summarization,
            _prompt_with_memories,
            untrusted_tool_results,
        ],
        context_schema=UserContext,
        checkpointer=get_checkpointer(),
        store=get_memory_store(),
        name="orbita_agent",  # nome do trace no LangSmith (padrão seria "LangGraph")
    )


def rollback_turn(agent: Agent, config: RunnableConfig, before: StateSnapshot) -> None:
    """Desfaz um turno que falhou no meio, voltando a conversa ao estado de `before`.

    Sem isso, o checkpoint pode ficar com a pergunta sem resposta ou com uma chamada de
    tool sem resultado, e a OpenAI recusa o próximo turno da conversa.

    Args:
        agent: Agente que executou o turno.
        config: Config do turno (com o thread_id).
        before: agent.get_state(config) lido antes de executar o turno.
    """
    if not before.values:  # conversa nova: não havia nada antes
        thread_id = config["configurable"]["thread_id"]
        agent.checkpointer.delete_thread(thread_id)  # type: ignore[union-attr]
        return
    # Cria um checkpoint a partir do anterior ao turno, que passa a ser o mais recente
    agent.update_state(before.config, None)
