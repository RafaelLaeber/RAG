"""Dependências compartilhadas dos routers: autenticação (JWT), permissão e agente."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyCookie, HTTPAuthorizationCredentials, HTTPBearer

from agentic_rag.agent.agent import Agent
from agentic_rag.auth.store import User, get_session_user
from agentic_rag.auth.tokens import decode_access_token

ACCESS_COOKIE = "vega_access"  # JWT de acesso, curto, enviado a toda a API
REFRESH_COOKIE = "vega_refresh"  # refresh token, longo, enviado só a /api/auth
REFRESH_PATH = "/api/auth"
LEGACY_SESSION_COOKIE = "vega_session"  # cookie da 1.x, apagado no login e no logout

# Os dois esquemas existem para o Swagger marcar as rotas protegidas com o cadeado.
# auto_error=False: a falta do token vira o 401 em português abaixo, não o erro padrão
_access_cookie = APIKeyCookie(
    name=ACCESS_COOKIE,
    auto_error=False,
    scheme_name="Cookie",
    description="JWT de acesso no cookie `vega_access`, criado por `POST /api/auth/login`, "
    "`/register` ou `/refresh`. No Swagger, basta fazer login pelo próprio endpoint.",
)
_bearer = HTTPBearer(
    auto_error=False,
    scheme_name="Bearer",
    bearerFormat="JWT",
    description="O mesmo JWT (`access_token` da resposta do login), no header "
    "`Authorization: Bearer <token>`. Para clientes fora do navegador.",
)

UNAUTHORIZED = "Sessão ausente ou expirada."


def current_user(
    request: Request,
    cookie: Annotated[str | None, Depends(_access_cookie)],
    bearer: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    """Usuário do JWT (header Bearer ou cookie); 401 se faltar, for inválido ou expirado.

    Além da assinatura, confere no banco que a sessão do token ainda existe, para logout,
    troca de senha e exclusão valerem na hora. O `session_id` fica em `request.state`.
    """
    token = bearer.credentials if bearer else cookie
    claims = decode_access_token(token) if token else None
    user = get_session_user(claims.user_id, claims.session_id) if claims else None
    if user is None or claims is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, UNAUTHORIZED, headers={"WWW-Authenticate": "Bearer"}
        )
    request.state.session_id = claims.session_id
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
