"""Usuários, sessões e tentativas de login em SQLite (storage/users.sqlite).

Senhas ficam só como hash argon2 e sessões só como hash SHA-256 do token: um vazamento do
banco não entrega senhas nem cookies válidos. As falhas de login ficam no banco (e não em
memória) para o bloqueio valer mesmo depois de reiniciar a API.
"""

import hashlib
import secrets
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from agentic_rag.config import get_settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions (user_id);
CREATE TABLE IF NOT EXISTS login_failures (
    key TEXT NOT NULL,
    failed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_login_failures ON login_failures (key, failed_at);
"""

_hasher = PasswordHasher()
# Hash de uma senha qualquer: login de e-mail inexistente também gasta o tempo de uma
# verificação, para o tempo de resposta não revelar quais e-mails existem
_DUMMY_HASH = _hasher.hash("senha-inexistente")


class EmailTakenError(Exception):
    """Já existe um usuário com esse e-mail."""


class TooManyAttemptsError(Exception):
    """Login bloqueado por excesso de falhas recentes."""

    def __init__(self, retry_after: int) -> None:
        super().__init__(f"tente de novo em {retry_after} s")
        self.retry_after = retry_after  # segundos até a próxima tentativa valer


@dataclass
class User:
    """Usuário cadastrado (sem o hash da senha)."""

    id: str
    name: str
    email: str
    is_admin: bool


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    """Abre uma conexão curta (uma por operação, segura para uso em threads) e confirma ao sair."""
    path = get_settings().users_db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(str(path), timeout=10)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(_SCHEMA)  # idempotente: cria as tabelas na primeira execução
        with conn:  # commit (ou rollback em caso de erro)
            yield conn


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


def _to_user(row: tuple[str, str, str, int]) -> User:
    return User(id=row[0], name=row[1], email=row[2], is_admin=bool(row[3]))


def create_user(name: str, email: str, password: str) -> User:
    """Cadastra um usuário. O primeiro cadastrado vira administrador.

    O papel é decidido dentro do próprio INSERT (um único comando), então dois registros
    simultâneos não conseguem ser admin ao mesmo tempo.

    Raises:
        EmailTakenError: Se o e-mail já estiver cadastrado.
    """
    user_id = str(uuid.uuid4())
    email = normalize_email(email)
    try:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO users (id, name, email, password_hash, is_admin, created_at) "
                "VALUES (?, ?, ?, ?, (SELECT COUNT(*) = 0 FROM users), ?)",
                (user_id, name, email, _hasher.hash(password), _now().isoformat()),
            )
            row = conn.execute(
                "SELECT id, name, email, is_admin FROM users WHERE id = ?", (user_id,)
            ).fetchone()
    except sqlite3.IntegrityError as exc:
        raise EmailTakenError(email) from exc
    return _to_user(row)


def authenticate(email: str, password: str) -> User | None:
    """Confere e-mail e senha. Devolve None para qualquer falha (sem dizer qual)."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, name, email, is_admin, password_hash FROM users WHERE email = ?",
            (normalize_email(email),),
        ).fetchone()
    try:
        _hasher.verify(row[4] if row else _DUMMY_HASH, password)
    except (VerificationError, InvalidHashError):
        return None
    return _to_user(row[:4]) if row else None


def _attempt_keys(email: str, ip: str) -> list[tuple[str, int]]:
    """Chaves contadas no login e o limite de cada uma."""
    settings = get_settings()
    return [
        (f"email:{normalize_email(email)}", settings.login_max_attempts),
        (f"ip:{ip}", settings.login_max_attempts_per_ip),
    ]


def check_login_allowed(email: str, ip: str) -> None:
    """Recusa a tentativa se o e-mail ou o IP passaram do limite de falhas na janela.

    A checagem vem antes de conferir a senha: durante o bloqueio, nem a senha certa entra,
    senão o atacante continuaria testando senhas e só não veria o resultado.

    Raises:
        TooManyAttemptsError: Com os segundos até a falha mais antiga sair da janela.
    """
    window = timedelta(minutes=get_settings().login_window_minutes)
    now = _now()
    retry_after = 0
    with _connect() as conn:
        for key, limit in _attempt_keys(email, ip):
            rows = conn.execute(
                "SELECT failed_at FROM login_failures WHERE key = ? AND failed_at > ? "
                "ORDER BY failed_at DESC LIMIT ?",
                (key, (now - window).isoformat(), limit),
            ).fetchall()
            if len(rows) >= limit:
                # Libera quando a limit-ésima falha mais recente sair da janela
                unlock = datetime.fromisoformat(rows[-1][0]) + window
                retry_after = max(retry_after, int((unlock - now).total_seconds()) + 1)
    if retry_after:
        raise TooManyAttemptsError(retry_after)


def record_login_failure(email: str, ip: str) -> None:
    """Conta uma falha de login para o e-mail e para o IP (e limpa as que saíram da janela)."""
    now = _now()
    cutoff = now - timedelta(minutes=get_settings().login_window_minutes)
    with _connect() as conn:
        conn.execute("DELETE FROM login_failures WHERE failed_at <= ?", (cutoff.isoformat(),))
        conn.executemany(
            "INSERT INTO login_failures (key, failed_at) VALUES (?, ?)",
            [(key, now.isoformat()) for key, _ in _attempt_keys(email, ip)],
        )


def clear_login_failures(email: str) -> None:
    """Zera as falhas do e-mail após um login certo.

    As do IP continuam: senão, quem tem uma conta poderia zerar o contador do próprio IP
    entrando nela entre uma tentativa e outra contra os e-mails dos outros.
    """
    with _connect() as conn:
        conn.execute(
            "DELETE FROM login_failures WHERE key = ?", (f"email:{normalize_email(email)}",)
        )


def create_session(user_id: str) -> str:
    """Abre uma sessão e devolve o token (só ele vai ao cookie; o banco guarda o hash)."""
    settings = get_settings()
    token = secrets.token_urlsafe(32)
    now = _now()
    expires = now + timedelta(hours=settings.session_ttl_hours)
    with _connect() as conn:
        # Aproveita o login para limpar as sessões vencidas
        conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now.isoformat(),))
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, created_at, expires_at) "
            "VALUES (?, ?, ?, ?)",
            (_hash_token(token), user_id, now.isoformat(), expires.isoformat()),
        )
    return token


def get_user_by_token(token: str) -> User | None:
    """Usuário dono de uma sessão válida (inexistente ou vencida = None)."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT u.id, u.name, u.email, u.is_admin FROM sessions s "
            "JOIN users u ON u.id = s.user_id "
            "WHERE s.token_hash = ? AND s.expires_at > ?",
            (_hash_token(token), _now().isoformat()),
        ).fetchone()
    return _to_user(row) if row else None


def delete_session(token: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_hash_token(token),))
