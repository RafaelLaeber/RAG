"""Chat com o agente, em streaming (Server-Sent Events)."""

import json
import uuid
from collections.abc import Iterator

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from agentic_rag.api.deps import AgentDep, CurrentUser
from agentic_rag.api.docs import errors
from agentic_rag.api.schemas import ChatIn
from agentic_rag.memory.conversations import conversation_owner
from agentic_rag.services.chat import ChatEvent, run_turn

router = APIRouter(prefix="/api/chat", tags=["chat"])

_EXAMPLE_TOOL = {"name": "search_policies", "args": {"query": "limite reembolso refeição viagem"}}
_EXAMPLE_ANSWER = "O limite é de R$ 110,00 por refeição."
# Exemplo do stream no Swagger, no mesmo formato que _sse gera
_SSE_EXAMPLE = "".join(
    f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
    for name, data in [
        ("conversation", {"id": "9a1c4f2e-5b3d-4c8a-a7e6-1f0d2b3c4e5f"}),
        ("reset", {}),
        ("tool", _EXAMPLE_TOOL),
        ("token", {"text": "O limite é de "}),
        ("token", {"text": "R$ 110,00 por refeição."}),
        ("answer", {"content": _EXAMPLE_ANSWER, "tools": [_EXAMPLE_TOOL]}),
        ("done", {}),
    ]
)


def _sse(events: Iterator[ChatEvent]) -> Iterator[str]:
    for event in events:
        yield f"event: {event.name}\ndata: {json.dumps(event.data(), ensure_ascii=False)}\n\n"


@router.post(
    "",
    summary="Perguntar ao agente (streaming)",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "Stream de eventos SSE (`text/event-stream`).",
            "content": {"text/event-stream": {"example": _SSE_EXAMPLE}},
        },
        **errors(401, (404, "`conversation_id` pertence a outro usuário.")),
    },
)
def chat(body: ChatIn, user: CurrentUser, agent: AgentDep) -> StreamingResponse:
    """Envia uma pergunta e recebe a resposta em **Server-Sent Events**, conforme o
    modelo escreve.

    Com `conversation_id: null`, começa uma conversa nova. Para continuar uma conversa,
    envie o id que veio no evento `conversation`.

    Cada evento tem a forma `event: <tipo>` + `data: <json>`:

    | Evento | `data` | Quando |
    |---|---|---|
    | `conversation` | `{"id"}` | Sempre o primeiro: o id da conversa |
    | `token` | `{"text"}` | Pedaço da resposta conforme o modelo escreve |
    | `reset` | `{}` | Descarte o texto recebido até aqui: o modelo vai chamar uma ferramenta |
    | `tool` | `{"name", "args"}` | O agente chamou uma ferramenta |
    | `answer` | `{"content", "tools"}` | Resposta final completa (substitui os `token`) |
    | `error` | `{"message"}` | O turno falhou e foi desfeito (não entra no histórico) |
    | `done` | `{}` | Sempre o último |

    Pergunta e resposta só entram no histórico quando o turno dá certo (`answer`).
    Por ser `POST`, leia com `fetch` e `ReadableStream`, não com `EventSource`.
    """
    conversation_id = body.conversation_id or str(uuid.uuid4())
    owner = conversation_owner(conversation_id)
    if owner is not None and owner != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversa não encontrada.")

    # O gerador é síncrono: o Starlette o consome no threadpool, sem bloquear o event loop
    return StreamingResponse(
        _sse(run_turn(agent, user.id, conversation_id, body.message)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
