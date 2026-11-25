"""Dependências compartilhadas dos routers: sessão, permissão e agente."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyCookie

from agentic_rag.agent.agent import Agent
from agentic_rag.auth.store import User, get_user_by_token

SESSION_COOKIE = "vega_session"

# Lê o mesmo cookie de antes; existe para o Swagger marcar as rotas protegidas com o cadeado.
# auto_error=False: a falta do cookie vira o 401 em português abaixo, não o 403 padrão
_session_cookie = APIKeyCookie(
    name=SESSION_COOKIE,
    auto_error=False,
    scheme_name="Sessão",
    description="Cookie criado por `POST /api/auth/login` ou `/register`. No Swagger, "
    "faça login pelo próprio endpoint: o navegador guarda o cookie sozinho.",
)


def current_user(token: Annotated[str | None, Depends(_session_cookie)]) -> User:
    """Usuário da sessão no cookie; 401 se não houver sessão válida."""
    user = get_user_by_token(token) if token else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão ausente ou expirada.")
    return user


def admin_user(user: Annotated[User, Depends(current_user)]) -> User:
    """Só administradores; 403 para os demais."""
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Apenas administradores.")
    return user


def get_agent_dep(request: Request) -> Agent:
    agent: Agent = request.app.state.agent
    return agent


CurrentUser = Annotated[User, Depends(current_user)]
AdminUser = Annotated[User, Depends(admin_user)]
AgentDep = Annotated[Agent, Depends(get_agent_dep)]
