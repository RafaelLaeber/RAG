"""Textos da documentação OpenAPI (Swagger em /api/docs).

Fica separado dos routers para eles mostrarem só a lógica de cada endpoint.
"""

from typing import Any

from agentic_rag.api.schemas import ErrorOut

DESCRIPTION = """
API do **Assistente Vega**: um agente RAG que responde sobre as políticas e documentos internos
de uma empresa e calcula reembolsos de despesas no exterior com a cotação real da moeda.

## Autenticação

Autenticação por **JWT** em dois tokens, criados no **registro** ou no **login**:

- **acesso**: JWT (HS256) válido por `ACCESS_TOKEN_MINUTES` (15). Vai no corpo da resposta
  (`access_token`) e no cookie `HttpOnly` `vega_access`. A API aceita o cookie ou o header
  `Authorization: Bearer <token>`;
- **refresh**: token opaco válido por `SESSION_TTL_HOURS` (7 dias), só no cookie `HttpOnly`
  `vega_refresh`, enviado apenas a `/api/auth`. `POST /api/auth/refresh` troca ele por um JWT
  novo.

Logout, troca de senha e exclusão do usuário invalidam os JWT na hora: a API confere no banco
que a sessão do token ainda existe.

Para testar por aqui:

1. Abra `POST /api/auth/register` (primeira vez) ou `POST /api/auth/login`, clique em
   **Try it out** e envie. O navegador guarda os cookies, e as demais rotas já funcionam.
   Outra opção: copie o `access_token` e cole em **Authorize → Bearer**.
2. Depois de 15 minutos, chame `POST /api/auth/refresh` para renovar o JWT.
3. `POST /api/auth/logout` encerra a sessão.

O **primeiro usuário registrado vira administrador**. Só administradores acessam
`/api/documents` e `/api/users`.

## Erros

Todo erro devolve `{"detail": "mensagem"}` em português, pronta para mostrar ao usuário.
Nos erros de validação (`422`), `detail` é uma lista com o campo e o motivo.

## Chat

`POST /api/chat` responde em **Server-Sent Events**. O Swagger mostra o stream inteiro só
quando ele termina. Para ver os eventos chegando, use o frontend ou `curl -N`.
"""

TAGS: list[dict[str, Any]] = [
    {"name": "auth", "description": "Registro, login, logout e usuário da sessão."},
    {"name": "chat", "description": "Conversa com o agente, com a resposta em streaming (SSE)."},
    {
        "name": "conversations",
        "description": "Histórico de conversas do usuário logado: listar, abrir e apagar.",
    },
    {
        "name": "documents",
        "description": "Base de conhecimento (`data/raw` e Astra DB). **Só administradores.**",
    },
    {
        "name": "users",
        "description": "Gestão de contas: listar, criar, alterar e apagar. **Só administradores.**",
    },
    {"name": "status", "description": "Saúde da API e configurações públicas."},
]

_DEFAULT_ERRORS = {
    401: "Sem JWT válido: ausente, inválido, expirado ou de uma sessão encerrada. "
    "Renove em `POST /api/auth/refresh` ou faça login.",
    403: "Apenas administradores.",
    404: "Não encontrado.",
}


def errors(*codes: int | tuple[int, str]) -> dict[int | str, dict[str, Any]]:
    """Respostas de erro para o `responses=` de uma rota.

    Cada item é um status (usa a descrição padrão) ou `(status, descrição)`. O `422` não
    entra aqui: o FastAPI já o documenta nas rotas com corpo ou parâmetros.
    """
    result: dict[int | str, dict[str, Any]] = {}
    for item in codes:
        code, text = item if isinstance(item, tuple) else (item, _DEFAULT_ERRORS[item])
        result[code] = {"model": ErrorOut, "description": text}
    return result
