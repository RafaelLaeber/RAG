"""Chat no terminal com o agente da Órbita.

Uso: python -m agentic_rag.cli
"""

import logging
import uuid

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from agentic_rag.agent.agent import get_agent
from agentic_rag.config import setup_langsmith

EXIT_COMMANDS = {"sair", "exit", "quit"}


def main() -> None:
    """Loop de conversa: cada execução do CLI é uma conversa (um thread_id)."""
    logging.basicConfig(level=logging.WARNING)
    tracing = setup_langsmith()
    agent = get_agent()
    config: RunnableConfig = {"configurable": {"thread_id": str(uuid.uuid4())}}

    print("Assistente Órbita (digite 'sair' para encerrar)")
    print(f"LangSmith: {'ligado' if tracing else 'desligado'}\n")

    while True:
        try:
            question = input("Você: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not question:
            continue
        if question.lower() in EXIT_COMMANDS:
            break

        # stream_mode="updates": recebe cada passo do agente (chamada de tool, resultado, resposta)
        for update in agent.stream(
            {"messages": [("user", question)]}, config, stream_mode="updates"
        ):
            for step in update.values():
                if not isinstance(step, dict):
                    continue
                for message in step.get("messages", []):
                    if isinstance(message, AIMessage) and message.tool_calls:
                        for call in message.tool_calls:
                            print(f"  [tool] {call['name']}({call['args']})")
                    elif isinstance(message, ToolMessage):
                        continue
                    elif isinstance(message, AIMessage):
                        print(f"\nAssistente: {message.text}\n")


if __name__ == "__main__":
    main()
