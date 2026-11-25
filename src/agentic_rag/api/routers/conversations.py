"""Histórico de conversas do usuário logado."""

from fastapi import APIRouter, HTTPException, Path, Response, status

from agentic_rag.api.deps import AgentDep, CurrentUser
from agentic_rag.api.docs import errors
from agentic_rag.api.schemas import (
    ConversationOut,
    ConversationSummaryOut,
    MessageOut,
    ToolCallOut,
)
from agentic_rag.memory.conversations import (
    delete_conversation,
    get_conversation,
    list_conversations,
    load_conversation,
)

router = APIRouter(prefix="/api/conversations", tags=["conversations"])

NOT_FOUND = "Conversa não encontrada."
_NOT_FOUND_DOC = (404, "A conversa não existe ou é de outro usuário.")

ConversationId = Path(description="Id da conversa (o mesmo do evento `conversation` do chat).")


@router.get(
    "",
    summary="Listar conversas",
    response_description="Conversas, da mais recente para a mais antiga.",
    responses=errors(401),
)
def list_all(user: CurrentUser) -> list[ConversationSummaryOut]:
    """Conversas do usuário logado, da mais recente para a mais antiga.

    Vêm no máximo `CONVERSATIONS_MAX_ITEMS` (30). Uma conversa só existe depois do primeiro
    turno que deu certo.
    """
    return [
        ConversationSummaryOut(id=c.id, title=c.title, updated_at=c.updated_at)
        for c in list_conversations(user.id)
    ]


@router.get(
    "/{conversation_id}",
    summary="Abrir conversa",
    response_description="Conversa com todas as mensagens.",
    responses=errors(401, _NOT_FOUND_DOC),
)
def get_one(user: CurrentUser, conversation_id: str = ConversationId) -> ConversationOut:
    """Conversa completa, com as mensagens em ordem e as ferramentas usadas em cada resposta.

    A conversa de outro usuário responde `404`, como se não existisse.
    """
    conversation = get_conversation(user.id, conversation_id)
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    messages = [
        MessageOut(
            role=m.role,
            content=m.content,
            tools=[ToolCallOut(name=t["name"], args=t["args"]) for t in m.tools],
        )
        for m in load_conversation(user.id, conversation_id)
    ]
    return ConversationOut(id=conversation.id, title=conversation.title, messages=messages)


@router.delete(
    "/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Apagar conversa",
    response_description="Conversa apagada.",
    responses=errors(401, _NOT_FOUND_DOC),
)
def delete_one(
    user: CurrentUser, agent: AgentDep, conversation_id: str = ConversationId
) -> Response:
    """Apaga a conversa de vez: o histórico (mensagens) e o contexto do agente (checkpoint).

    Não dá para desfazer. As memórias de longo prazo do usuário continuam.
    """
    if not delete_conversation(user.id, conversation_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    agent.checkpointer.delete_thread(conversation_id)  # type: ignore[union-attr]
    return Response(status_code=status.HTTP_204_NO_CONTENT)
