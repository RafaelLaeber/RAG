# Contrato da API do Assistente Vega

API FastAPI em `src/agentic_rag/api/`, servida em `http://localhost:8000` com prefixo `/api`.
O frontend React (`frontend/`) consome só estes endpoints. **Rotas sem barra no fim:** nas
tabelas, `/` significa o próprio prefixo (ex.: `GET /api/documents`, não `/api/documents/`). Com o
build do React servido pela API, uma rota com barra a mais cai no fallback do SPA e responde `404`. JSON em UTF-8, campos em
`snake_case`, datas em ISO 8601 com fuso (UTC).

## Autenticação

- Sessão opaca: no login ou registro, a API cria um token aleatório (`secrets.token_urlsafe(32)`),
  guarda **só o hash SHA-256** dele na tabela `sessions` e devolve o token no cookie
  `vega_session` (`HttpOnly`, `SameSite=Lax`, `Path=/`, `Secure` configurável por
  `SESSION_COOKIE_SECURE`, validade `SESSION_TTL_HOURS`, padrão 168 h).
- O frontend não guarda token: o navegador manda o cookie. Em desenvolvimento, o Vite faz
  proxy de `/api` para a API, então tudo fica na mesma origem.
- Rotas protegidas sem sessão válida respondem `401`. Rotas de administrador respondem `403`
  para quem não é admin.
- O **primeiro usuário registrado vira administrador** (`is_admin = true`). Só admins mexem na
  base de conhecimento.
- O `user_id` usado pelo agente (memórias, histórico, checkpoints) é o `id` do usuário logado.

## Erros

Todo erro devolve `{"detail": "mensagem em português"}` com o status adequado (`400`, `401`,
`403`, `404`, `409`, `413`, `422`, `429`). A mensagem pode ser mostrada direto ao usuário. Erros de
validação do FastAPI (`422`) também chegam em `detail`, mas como lista.

## Tipos

```ts
type User = { id: string; name: string; email: string; is_admin: boolean };
type ConversationSummary = { id: string; title: string; updated_at: string };
type ToolCall = { name: string; args: Record<string, unknown> };
type Message = { role: "user" | "assistant"; content: string; tools: ToolCall[] };
type DataFile = { name: string; size: number };
type UploadCheck = {
  name: string; size: number; ok: boolean; error: string | null;
  injection_signals: string[]; replaces: boolean;
};
type IngestionResult = { total: number; added: number; deleted: number };
```

## Endpoints

### Status

| Método | Rota | Auth | Corpo | Resposta |
|---|---|---|---|---|
| GET | `/api/health` | não | | `{"status": "ok"}` |
| GET | `/api/meta` | sim | | `{"llm_model": str, "langsmith": bool, "upload_max_mb": int, "supported_extensions": [".md", ".pdf", ".txt"]}` |

### Auth (`/api/auth`)

| Método | Rota | Auth | Corpo | Resposta |
|---|---|---|---|---|
| POST | `/register` | não | `{"name": str, "email": str, "password": str}` | `201` `Auth` + cookies |
| POST | `/login` | não | `{"email": str, "password": str}` | `200` `Auth` + cookies |
| POST | `/refresh` | cookie `vega_refresh` | | `200` `Auth` + cookie `vega_access` novo; `401` se a sessão acabou |
| POST | `/logout` | não | | `204`, apaga a sessão e os cookies |
| GET | `/me` | sim | | `User` |

`Auth` = `{"user": User, "access_token": str, "token_type": "bearer", "expires_in": int}`.

**Tokens:**
- **Acesso**: JWT HS256 com `sub` (id do usuário), `sid` (id da sessão), `typ: "access"`,
  `iss: "vega"`, `iat` e `exp`. Vale `ACCESS_TOKEN_MINUTES` (padrão 15). Vai no corpo e no
  cookie `vega_access` (`HttpOnly`, `SameSite=Lax`, `Path=/`). Rotas com "Auth: sim" aceitam
  esse cookie ou o header `Authorization: Bearer <token>`.
- **Refresh**: token opaco que vale `SESSION_TTL_HOURS` (padrão 168), só no cookie
  `vega_refresh` (`HttpOnly`, `SameSite=Lax`, `Path=/api/auth`). O banco guarda só o SHA-256.
- Um JWT só vale enquanto a sessão (`sid`) existir: logout, troca de senha e exclusão do
  usuário o invalidam na hora. O papel (`is_admin`) é lido do banco a cada requisição.
- JWT ausente, inválido ou vencido: `401` com `WWW-Authenticate: Bearer`. O frontend chama
  `/refresh` uma vez e repete a requisição; se o refresh também falhar, vai para o login.

- `name`: 1 a 80 caracteres após `strip`. `email`: válido, normalizado em minúsculas.
  `password`: 8 a 128 caracteres.
- E-mail já cadastrado: `409` "Já existe uma conta com esse e-mail."
- Login inválido (e-mail inexistente ou senha errada): `401` "E-mail ou senha incorretos."
- Limite de tentativas: depois de `LOGIN_MAX_ATTEMPTS` falhas (padrão 5) no mesmo e-mail, ou
  `LOGIN_MAX_ATTEMPTS_PER_IP` (padrão 20) no mesmo IP, dentro de `LOGIN_WINDOW_MINUTES`
  (padrão 15), o login responde `429` "Muitas tentativas de login. Tente de novo em N minuto(s).",
  com o header `Retry-After` em segundos. Durante o bloqueio, nem a senha certa entra. Um login
  certo zera as falhas do e-mail (as do IP continuam).

### Conversas (`/api/conversations`)

| Método | Rota | Auth | Resposta |
|---|---|---|---|
| GET | `/` | sim | `ConversationSummary[]`, da mais recente para a mais antiga (até `CONVERSATIONS_MAX_ITEMS`) |
| GET | `/{id}` | sim | `{"id": str, "title": str, "messages": Message[]}`; `404` se não existir ou for de outro usuário |
| DELETE | `/{id}` | sim | `204`; apaga histórico e checkpoint; `404` se não for do usuário |

### Chat (`/api/chat`)

`POST /api/chat` (auth), corpo `{"conversation_id": str | null, "message": str}` (`message` de 1 a
4000 caracteres após `strip`). `conversation_id: null` começa uma conversa nova. Um id que já
existe e é de outro usuário responde `404`.

A resposta é `text/event-stream` (SSE). Como é `POST`, o frontend lê com `fetch` + `ReadableStream`
(não `EventSource`). Cada evento tem a forma:

```
event: <tipo>
data: <json>

```

| Evento | `data` | Quando |
|---|---|---|
| `conversation` | `{"id": str}` | Sempre o primeiro: o id da conversa (novo se `conversation_id` era `null`) |
| `token` | `{"text": str}` | Pedaço da resposta conforme o modelo escreve |
| `reset` | `{}` | Descarte o texto recebido até aqui: o modelo vai chamar uma tool |
| `tool` | `{"name": str, "args": {...}}` | O agente chamou uma ferramenta |
| `answer` | `{"content": str, "tools": ToolCall[]}` | Resposta final completa (substitui o texto dos `token`) |
| `error` | `{"message": str}` | O turno falhou e foi desfeito; mensagem amigável, sem detalhe técnico |
| `done` | `{}` | Sempre o último |

Regras do backend (as mesmas do Streamlit antigo):
- Só tokens do nó `model` viram `token` (o resumo também chama o LLM).
- Nos `updates`, só os nós `model` e `PromptProtection.before_agent` são lidos.
- Em falha: log com `logger.exception`, `rollback_turn` e evento `error`. O turno não entra no
  histórico.
- Em sucesso: `save_turn` grava pergunta e resposta juntas antes do `answer`.
- Conversa sem checkpoint mas com histórico salvo: reconstrói o contexto com `to_agent_messages`.

### Base de conhecimento (`/api/documents`, só admin)

| Método | Rota | Corpo | Resposta |
|---|---|---|---|
| GET | `/` | | `DataFile[]` (arquivos de `data/raw`, por nome) |
| DELETE | `/` | | `{"removed": int}`: apaga todos os arquivos de `data/raw` e todos os chunks do Astra; falha do Astra responde `502` (nada é apagado) |
| DELETE | `/{name}` | | `204`; apaga um arquivo de `data/raw` e os chunks dele no Astra. `404` se não existir, `502` se o Astra falhar (nada é apagado) |
| POST | `/check` | `multipart/form-data`, campo `files` (um ou mais) | `UploadCheck[]`, sem gravar nada |
| POST | `/` | `multipart/form-data`, campo `files` | `{"saved": str[], "errors": [{"name": str, "message": str}], "ingestion": IngestionResult \| null, "ingestion_error": str \| null}` |
| POST | `/ingest` | | `IngestionResult`; falha da ingestão responde `502` com `detail` |

- Arquivo acima de `UPLOAD_MAX_MB`: recusado em `UploadCheck.error` (não derruba a requisição).
- `POST /` só grava os válidos e roda a ingestão se gravou pelo menos um.

### Usuários (`/api/users`, só admin)

| Método | Rota | Corpo | Resposta |
|---|---|---|---|
| GET | `/` | | `User[]`, por nome |
| POST | `/` | `{"name": str, "email": str, "password": str, "is_admin": bool}` (`is_admin` opcional, padrão `false`) | `201` + `User`; `409` se o e-mail já existir. Não abre sessão |
| PATCH | `/{id}` | qualquer subconjunto de `{"name", "email", "password", "is_admin"}` (omitido = não muda) | `User`; `404` se não existir, `409` se o e-mail já for de outra conta ou se a mudança deixaria o sistema sem admin |
| DELETE | `/{id}` | | `204`; apaga a conta, sessões, conversas, checkpoints e memórias do usuário. `404` se não existir, `409` para a própria conta ou o último admin |

- Mesmas validações do registro: nome de 1 a 80 caracteres, e-mail válido, senha de 8 a 128.
- Trocar a senha encerra as sessões abertas do usuário. Se for a própria conta, a sessão atual continua.
- Ninguém tira o próprio acesso de administrador (`409`) nem apaga a própria conta.
