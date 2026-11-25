export type User = { id: string; name: string; email: string; is_admin: boolean }
export type AuthResponse = {
  user: User
  access_token: string
  token_type: 'bearer'
  expires_in: number
}
export type UserCreate = { name: string; email: string; password: string; is_admin: boolean }
/** Campos omitidos ficam como estão. */
export type UserUpdate = Partial<UserCreate>
export type ConversationSummary = { id: string; title: string; updated_at: string }
export type ToolCall = { name: string; args: Record<string, unknown> }
export type Message = { role: 'user' | 'assistant'; content: string; tools: ToolCall[] }
export type ConversationDetail = { id: string; title: string; messages: Message[] }
export type DataFile = { name: string; size: number }
export type UploadCheck = {
  name: string
  size: number
  ok: boolean
  error: string | null
  injection_signals: string[]
  replaces: boolean
}
export type IngestionResult = { total: number; added: number; deleted: number }
export type UploadResult = {
  saved: string[]
  errors: { name: string; message: string }[]
  ingestion: IngestionResult | null
  ingestion_error: string | null
}
export type Meta = {
  llm_model: string
  langsmith: boolean
  upload_max_mb: number
  supported_extensions: string[]
}

export type ChatEvent =
  | { type: 'conversation'; data: { id: string } }
  | { type: 'token'; data: { text: string } }
  | { type: 'reset'; data: Record<string, never> }
  | { type: 'tool'; data: ToolCall }
  | { type: 'answer'; data: { content: string; tools: ToolCall[] } }
  | { type: 'error'; data: { message: string } }
  | { type: 'done'; data: Record<string, never> }
