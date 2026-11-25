import { readEvents } from './sse'
import type {
  ChatEvent,
  ConversationDetail,
  ConversationSummary,
  DataFile,
  IngestionResult,
  Meta,
  UploadCheck,
  UploadResult,
  User,
} from './types'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

let onUnauthorized: (() => void) | null = null
/** O contexto de autenticação registra aqui o que fazer quando uma rota protegida responde 401. */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler
}

const GENERIC_ERROR = 'Não foi possível concluir a operação. Tente de novo.'

/** `detail` é texto ou, nos 422 do FastAPI, uma lista de erros. */
function detailToMessage(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) =>
        d && typeof d === 'object' && 'msg' in d ? String((d as { msg: unknown }).msg) : '',
      )
      .filter(Boolean)
    if (msgs.length) return msgs.join(' ')
  }
  return GENERIC_ERROR
}

async function toError(res: Response): Promise<ApiError> {
  let message = GENERIC_ERROR
  try {
    const body: unknown = await res.json()
    if (body && typeof body === 'object' && 'detail' in body) {
      message = detailToMessage((body as { detail: unknown }).detail)
    }
  } catch {
    /* corpo sem JSON: mantém a mensagem genérica */
  }
  return new ApiError(res.status, message)
}

async function send(path: string, init: RequestInit = {}, authRoute = false): Promise<Response> {
  let res: Response
  try {
    res = await fetch(path, { credentials: 'same-origin', ...init })
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err
    throw new ApiError(0, 'Sem conexão com o servidor. Verifique sua rede e tente de novo.')
  }
  if (!res.ok) {
    // 401 em rotas de login/registro/me é "senha errada" ou "sem sessão", não sessão expirada.
    if (res.status === 401 && !authRoute) onUnauthorized?.()
    throw await toError(res)
  }
  return res
}

async function json<T>(path: string, init?: RequestInit, authRoute = false): Promise<T> {
  const res = await send(path, init, authRoute)
  return (await res.json()) as T
}

function post<T>(path: string, body?: unknown, authRoute = false): Promise<T> {
  return json<T>(
    path,
    {
      method: 'POST',
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    },
    authRoute,
  )
}

function filesForm(files: File[]): FormData {
  const form = new FormData()
  for (const f of files) form.append('files', f)
  return form
}

export const api = {
  register: (name: string, email: string, password: string) =>
    post<User>('/api/auth/register', { name, email, password }, true),
  login: (email: string, password: string) =>
    post<User>('/api/auth/login', { email, password }, true),
  logout: async () => {
    await send('/api/auth/logout', { method: 'POST' }, true)
  },
  me: () => json<User>('/api/auth/me', undefined, true),
  meta: () => json<Meta>('/api/meta'),

  listConversations: () => json<ConversationSummary[]>('/api/conversations'),
  getConversation: (id: string) =>
    json<ConversationDetail>(`/api/conversations/${encodeURIComponent(id)}`),
  deleteConversation: async (id: string) => {
    await send(`/api/conversations/${encodeURIComponent(id)}`, { method: 'DELETE' })
  },

  listDocuments: () => json<DataFile[]>('/api/documents'),
  checkDocuments: (files: File[]) =>
    json<UploadCheck[]>('/api/documents/check', { method: 'POST', body: filesForm(files) }),
  uploadDocuments: (files: File[]) =>
    json<UploadResult>('/api/documents', { method: 'POST', body: filesForm(files) }),
  ingest: () => post<IngestionResult>('/api/documents/ingest'),
}

/** Abre o stream SSE do chat. Lança ApiError se a resposta inicial falhar (401, 404, 422...). */
export async function* streamChat(
  conversationId: string | null,
  message: string,
  signal?: AbortSignal,
): AsyncGenerator<ChatEvent> {
  const res = await send('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({ conversation_id: conversationId, message }),
    signal,
  })
  if (!res.body) throw new ApiError(0, 'A resposta do servidor veio vazia.')
  yield* readEvents(res.body)
}
