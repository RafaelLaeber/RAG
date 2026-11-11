"""Chat no terminal com o agente da Órbita.

Uso: python -m agentic_rag.cli
"""

import logging
import uuid

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from agentic_rag.agent.agent import get_agent
from agentic_rag.config import get_settings, setup_langsmith
from agentic_rag.memory.store import UserContext

EXIT_COMMANDS = {"sair", "exit", "quit"}


def main() -> None:
    """Loop de conversa: cada execução é uma conversa nova (thread_id), mesmo usuário (user_id)."""
    logging.basicConfig(level=logging.WARNING)
    tracing = setup_langsmith()
    agent = get_agent()
    config: RunnableConfig = {"configurable": {"thread_id": str(uuid.uuid4())}}
    context = UserContext(user_id=get_settings().user_id)

    print("Assistente Órbita (digite 'sair' para encerrar)")
    print(f"LangSmith: {'ligado' if tracing else 'desligado'} | usuário: {context.user_id}\n")

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
            {"messages": [("user", question)]}, config, context=context, stream_mode="updates"
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
