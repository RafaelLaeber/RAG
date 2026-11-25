"""Gestão de usuários: listar, criar, alterar e apagar contas (só administradores)."""

import logging

from fastapi import APIRouter, HTTPException, Path, Request, Response, status

from agentic_rag.api.deps import AdminUser, AgentDep
from agentic_rag.api.docs import errors
from agentic_rag.api.schemas import UserCreateIn, UserOut, UserUpdateIn
from agentic_rag.auth.store import (
    EmailTakenError,
    LastAdminError,
    User,
    add_user,
    delete_user,
    list_users,
    update_user,
)
from agentic_rag.memory.conversations import delete_user_conversations
from agentic_rag.memory.store import delete_all_user_memories, get_memory_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/users", tags=["users"], responses=errors(401, 403))

NOT_FOUND = "Usuário não encontrado."
EMAIL_TAKEN = "Já existe uma conta com esse e-mail."
LAST_ADMIN = "É preciso manter pelo menos um administrador."

UserId = Path(description="Id do usuário (uuid4).")


def _out(user: User) -> UserOut:
    return UserOut(id=user.id, name=user.name, email=user.email, is_admin=user.is_admin)


@router.get("", summary="Listar usuários", response_description="Usuários, por nome.")
def list_all(_admin: AdminUser) -> list[UserOut]:
    """Todas as contas cadastradas, sem senha."""
    return [_out(u) for u in list_users()]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Criar usuário",
    response_description="Usuário criado.",
    responses=errors((409, EMAIL_TAKEN)),
)
def create(body: UserCreateIn, _admin: AdminUser) -> UserOut:
    """Cria uma conta já com o papel escolhido. Não abre sessão: o usuário entra pelo login."""
    try:
        return _out(add_user(body.name, body.email, body.password, body.is_admin))
    except EmailTakenError:
        raise HTTPException(status.HTTP_409_CONFLICT, EMAIL_TAKEN) from None


@router.patch(
    "/{user_id}",
    summary="Alterar usuário",
    response_description="Usuário atualizado.",
    responses=errors(
        (404, NOT_FOUND),
        (409, "E-mail já usado, ou a mudança tiraria o último administrador."),
    ),
)
def update(
    body: UserUpdateIn, request: Request, admin: AdminUser, user_id: str = UserId
) -> UserOut:
    """Altera nome, e-mail, senha e/ou papel. Campos omitidos ficam como estão.

    Trocar a senha encerra as sessões abertas do usuário (menos a sua, se for a própria
    conta). Ninguém tira o próprio acesso de administrador, e o sistema sempre mantém pelo
    menos um.
    """
    if user_id == admin.id and body.is_admin is False:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Você não pode tirar o seu próprio acesso de administrador."
        )
    try:
        user = update_user(
            user_id,
            name=body.name,
            email=body.email,
            password=body.password,
            is_admin=body.is_admin,
            keep_session=request.state.session_id if user_id == admin.id else None,
        )
    except EmailTakenError:
        raise HTTPException(status.HTTP_409_CONFLICT, EMAIL_TAKEN) from None
    except LastAdminError:
        raise HTTPException(status.HTTP_409_CONFLICT, LAST_ADMIN) from None
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return _out(user)


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Apagar usuário",
    response_description="Usuário e dados dele apagados.",
    responses=errors((404, NOT_FOUND), (409, "Não dá para apagar a própria conta.")),
)
def delete(admin: AdminUser, agent: AgentDep, user_id: str = UserId) -> Response:
    """Apaga a conta, as sessões, o histórico de conversas, o contexto do agente
    (checkpoints) e as memórias de longo prazo do usuário. Não dá para desfazer.
    """
    if user_id == admin.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Você não pode apagar a sua própria conta.")
    try:
        found = delete_user(user_id)
    except LastAdminError:
        raise HTTPException(status.HTTP_409_CONFLICT, LAST_ADMIN) from None
    if not found:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)

    for thread_id in delete_user_conversations(user_id):
        agent.checkpointer.delete_thread(thread_id)  # type: ignore[union-attr]
    removed = delete_all_user_memories(get_memory_store(), user_id)
    logger.info("Usuário %s apagado (%d memória(s))", user_id, removed)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
