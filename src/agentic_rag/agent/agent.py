"""Factory do agente: LLM + tools (RAG e câmbio) + memória da conversa"""

from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph

from agentic_rag.agent.prompts import SYSTEM_PROMPT
from agentic_rag.llm import get_chat_model
from agentic_rag.tools.api_tool import get_exchange_rate
from agentic_rag.tools.rag_tool import search_policies


def get_agent() -> CompiledStateGraph:
    """Cria o agente ReAct com tool calling e memória de curto prazo.

    A memória é guardada pelo checkpointer, separada por thread_id
    (passado em config={"configurable": {"thread_id": ...}}).

    Returns:
        Agente executável com invoke/stream.
    """
    return create_agent(
        model=get_chat_model(),
        tools=[search_policies, get_exchange_rate],
        system_prompt=SYSTEM_PROMPT,
        checkpointer=InMemorySaver(),
        name="orbita_agent",  # nome do trace no LangSmith (padrão seria "LangGraph")
    )
