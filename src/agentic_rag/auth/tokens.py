"""Token de acesso JWT (HS256).

O JWT é curto (`access_token_minutes`) e leva o usuário (`sub`) e a sessão (`sid`, o hash do
refresh token guardado em `sessions`). A API confere a assinatura e a validade e, mesmo
assim, confirma no banco que a sessão ainda existe: logout, troca de senha e exclusão do
usuário valem na hora, sem esperar o token expirar.
"""

import logging
import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache

import jwt

from agentic_rag.config import get_settings

logger = logging.getLogger(__name__)

ALGORITHM = "HS256"
ISSUER = "vega"
_TOKEN_TYPE = "access"


@dataclass(frozen=True)
class AccessClaims:
    """O que a API usa de um JWT válido."""

    user_id: str
    session_id: str  # hash do refresh token (chave da tabela sessions)


@lru_cache
def _secret() -> str:
    """Chave de assinatura: `JWT_SECRET` do .env ou, sem ela, um arquivo gerado uma vez.

    O arquivo fica em `storage/` (fora do git) com permissão só do dono, onde o SO permitir.
    Trocar a chave invalida todos os JWT em circulação (o frontend renova pelo refresh).
    """
    settings = get_settings()
    if settings.jwt_secret and settings.jwt_secret.get_secret_value():
        return settings.jwt_secret.get_secret_value()
    path = settings.jwt_secret_path
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    path.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_urlsafe(64)
    # O_EXCL: se outro processo criou o arquivo ao mesmo tempo, usa o dele
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return path.read_text(encoding="utf-8").strip()
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(key)
    logger.info("JWT_SECRET ausente: chave gerada em %s", path)
    return key


def create_access_token(user_id: str, session_id: str) -> tuple[str, int]:
    """Emite um JWT de acesso. Devolve o token e a validade em segundos."""
    ttl = timedelta(minutes=get_settings().access_token_minutes)
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "sid": session_id,
        "typ": _TOKEN_TYPE,
        "iss": ISSUER,
        "iat": now,
        "exp": now + ttl,
    }
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM), int(ttl.total_seconds())


def decode_access_token(token: str) -> AccessClaims | None:
    """Confere assinatura, emissor, validade e tipo. None para qualquer token inválido."""
    try:
        payload = jwt.decode(
            token,
            _secret(),
            algorithms=[ALGORITHM],  # fixo: recusa "none" e troca de algoritmo
            issuer=ISSUER,
            options={"require": ["sub", "sid", "exp", "iat", "iss"]},
        )
    except jwt.PyJWTError:
        return None
    if payload.get("typ") != _TOKEN_TYPE:
        return None
    return AccessClaims(user_id=str(payload["sub"]), session_id=str(payload["sid"]))
