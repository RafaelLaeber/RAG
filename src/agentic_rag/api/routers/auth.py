"""Registro, login, renovação do JWT, logout e usuário atual.

Autenticação em dois tokens:
- **acesso**: JWT curto (`ACCESS_TOKEN_MINUTES`), no cookie `vega_access` e no corpo da
  resposta, aceito também em `Authorization: Bearer`;
- **refresh**: token opaco e longo (`SESSION_TTL_HOURS`), só no cookie `vega_refresh`,
  que o navegador envia apenas para `/api/auth`. Serve para pedir um JWT novo em `/refresh`.
"""

from fastapi import APIRouter, HTTPException, Request, Response, status

from agentic_rag.api.deps import (
    ACCESS_COOKIE,
    LEGACY_SESSION_COOKIE,
    REFRESH_COOKIE,
    REFRESH_PATH,
    CurrentUser,
)
from agentic_rag.api.docs import errors
from agentic_rag.api.schemas import AuthOut, LoginIn, RegisterIn, UserOut
from agentic_rag.auth.store import (
    EmailTakenError,
    TooManyAttemptsError,
    User,
    authenticate,
    check_login_allowed,
    clear_login_failures,
    create_session,
    create_user,
    delete_session,
    get_user_by_refresh_token,
    record_login_failure,
)
from agentic_rag.auth.tokens import create_access_token
from agentic_rag.config import get_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _user_out(user: User) -> UserOut:
    return UserOut(id=user.id, name=user.name, email=user.email, is_admin=user.is_admin)


def _set_cookie(response: Response, name: str, value: str, max_age: int, path: str) -> None:
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=get_settings().session_cookie_secure,
        path=path,
    )


def _issue_access(response: Response, user: User, session_id: str) -> AuthOut:
    """Emite o JWT de acesso, grava no cookie e monta a resposta."""
    token, expires_in = create_access_token(user.id, session_id)
    _set_cookie(response, ACCESS_COOKIE, token, expires_in, "/")
    return AuthOut(user=_user_out(user), access_token=token, expires_in=expires_in)


def _open_session(response: Response, user: User) -> AuthOut:
    """Cria a sessão (refresh token) e o primeiro JWT de acesso."""
    refresh, session_id = create_session(user.id)
    _set_cookie(
        response,
        REFRESH_COOKIE,
        refresh,
        get_settings().session_ttl_hours * 3600,
        REFRESH_PATH,
    )
    response.delete_cookie(LEGACY_SESSION_COOKIE, path="/")
    return _issue_access(response, user, session_id)


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    summary="Criar conta",
    response_description="Conta criada e sessão aberta (JWT de acesso e refresh token).",
    responses=errors((409, "Já existe uma conta com esse e-mail.")),
)
def register(body: RegisterIn, response: Response) -> AuthOut:
    """Cria a conta e já abre a sessão: o usuário sai do registro logado.

    O e-mail é normalizado em minúsculas e precisa ser único. A senha é guardada só como
    hash argon2. O **primeiro usuário registrado vira administrador**.
    """
    try:
        user = create_user(body.name, body.email, body.password)
    except EmailTakenError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Já existe uma conta com esse e-mail."
        ) from None
    return _open_session(response, user)


@router.post(
    "/login",
    summary="Entrar",
    response_description="Login certo: JWT de acesso (corpo e cookie) e refresh token (cookie).",
    responses=errors(
        (401, "E-mail ou senha incorretos (a mesma mensagem nos dois casos)."),
        (
            429,
            "Muitas tentativas: login bloqueado por um tempo. "
            "O header `Retry-After` diz em quantos segundos tentar de novo.",
        ),
    ),
)
def login(body: LoginIn, request: Request, response: Response) -> AuthOut:
    """Confere e-mail e senha e abre uma sessão.

    O JWT de acesso vale `ACCESS_TOKEN_MINUTES` (15); a sessão, `SESSION_TTL_HOURS` (7
    dias), renovando o JWT em `POST /api/auth/refresh`.

    **Limite de tentativas:** depois de `LOGIN_MAX_ATTEMPTS` falhas (5) no mesmo e-mail, ou
    `LOGIN_MAX_ATTEMPTS_PER_IP` (20) vindas do mesmo IP, dentro de `LOGIN_WINDOW_MINUTES`
    (15), o login responde `429`, mesmo com a senha certa. Um login certo zera as falhas do
    e-mail.
    """
    # Atrás de um proxy reverso, este é o IP do proxy: aí é preciso rodar o uvicorn com
    # --proxy-headers para ele ler o X-Forwarded-For
    ip = request.client.host if request.client else "desconhecido"
    try:
        check_login_allowed(body.email, ip)
    except TooManyAttemptsError as exc:
        minutes = -(-exc.retry_after // 60)  # arredonda para cima
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Muitas tentativas de login. Tente de novo em {minutes} minuto(s).",
            headers={"Retry-After": str(exc.retry_after)},
        ) from None

    user = authenticate(body.email, body.password)
    if user is None:
        record_login_failure(body.email, ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-mail ou senha incorretos.")
    clear_login_failures(body.email)
    return _open_session(response, user)


@router.post(
    "/refresh",
    summary="Renovar o JWT",
    response_description="JWT de acesso novo (corpo e cookie).",
    responses=errors((401, "Refresh token ausente, vencido ou encerrado: faça login de novo.")),
)
def refresh(request: Request, response: Response) -> AuthOut:
    """Troca o refresh token (cookie `vega_refresh`) por um JWT de acesso novo.

    A interface chama esta rota sozinha quando a API responde `401`. A sessão continua a
    mesma; só o JWT é renovado.
    """
    token = request.cookies.get(REFRESH_COOKIE)
    found = get_user_by_refresh_token(token) if token else None
    if found is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Sessão ausente ou expirada. Entre de novo."
        )
    user, session_id = found
    return _issue_access(response, user, session_id)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Sair",
    response_description="Sessão encerrada e cookies apagados.",
)
def logout(request: Request) -> Response:
    """Encerra a sessão: o refresh token é apagado do banco e os cookies, do navegador.

    Não exige JWT válido (sair com o acesso já vencido também funciona). Os JWT emitidos
    para essa sessão deixam de valer na hora, porque a API confere a sessão no banco.
    """
    if token := request.cookies.get(REFRESH_COOKIE):
        delete_session(token)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_PATH)
    response.delete_cookie(LEGACY_SESSION_COOKIE, path="/")
    return response


@router.get(
    "/me",
    summary="Usuário da sessão",
    response_description="Usuário logado.",
    responses=errors(401),
)
def me(user: CurrentUser) -> UserOut:
    """Devolve o usuário dono do JWT de acesso.

    `401` significa JWT ausente ou vencido: a interface tenta `POST /api/auth/refresh` e,
    se também falhar, manda para o login.
    """
    return _user_out(user)
