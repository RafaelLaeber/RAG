"""Registro, login, logout e usuário atual."""

from fastapi import APIRouter, HTTPException, Request, Response, status

from agentic_rag.api.deps import SESSION_COOKIE, CurrentUser
from agentic_rag.api.docs import errors
from agentic_rag.api.schemas import LoginIn, RegisterIn, UserOut
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
    record_login_failure,
)
from agentic_rag.config import get_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _user_out(user: User) -> UserOut:
    return UserOut(id=user.id, name=user.name, email=user.email, is_admin=user.is_admin)


def _open_session(response: Response, user: User) -> None:
    settings = get_settings()
    response.set_cookie(
        SESSION_COOKIE,
        create_session(user.id),
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
        path="/",
    )


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    summary="Criar conta",
    response_description="Conta criada e sessão aberta (cookie `vega_session`).",
    responses=errors((409, "Já existe uma conta com esse e-mail.")),
)
def register(body: RegisterIn, response: Response) -> UserOut:
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
    _open_session(response, user)
    return _user_out(user)


@router.post(
    "/login",
    summary="Entrar",
    response_description="Login certo: sessão aberta (cookie `vega_session`).",
    responses=errors(
        (401, "E-mail ou senha incorretos (a mesma mensagem nos dois casos)."),
        (
            429,
            "Muitas tentativas: login bloqueado por um tempo. "
            "O header `Retry-After` diz em quantos segundos tentar de novo.",
        ),
    ),
)
def login(body: LoginIn, request: Request, response: Response) -> UserOut:
    """Confere e-mail e senha e abre uma sessão, válida por `SESSION_TTL_HOURS` (7 dias).

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
    _open_session(response, user)
    return _user_out(user)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Sair",
    response_description="Sessão encerrada e cookie apagado.",
    responses=errors(401),
)
def logout(request: Request, _user: CurrentUser) -> Response:
    """Encerra a sessão atual: o token é apagado do banco e o cookie, do navegador."""
    if token := request.cookies.get(SESSION_COOKIE):
        delete_session(token)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@router.get(
    "/me",
    summary="Usuário da sessão",
    response_description="Usuário logado.",
    responses=errors(401),
)
def me(user: CurrentUser) -> UserOut:
    """Devolve o usuário dono do cookie de sessão.

    A interface chama esta rota ao abrir a página: `401` significa que é preciso fazer
    login.
    """
    return _user_out(user)
