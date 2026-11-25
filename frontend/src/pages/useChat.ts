import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError, streamChat } from '../api/client'
import type { ConversationSummary, ToolCall } from '../api/types'

export type UiMessage = {
  role: 'user' | 'assistant'
  content: string
  tools: ToolCall[]
  /** Mensagem de erro do turno: só existe na tela, não vai para o histórico. */
  error?: boolean
}

export type LiveTurn = { text: string; status: string; tools: ToolCall[] }

const THINKING = 'Pensando…'

function errorText(err: unknown): string {
  return err instanceof ApiError ? err.message : 'Não consegui responder agora. Tente de novo.'
}

export function useChat() {
  const [conversations, setConversations] = useState<ConversationSummary[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [messages, setMessages] = useState<UiMessage[]>([])
  const [live, setLive] = useState<LiveTurn | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const busy = live !== null

  const refreshConversations = useCallback(async () => {
    try {
      setConversations(await api.listConversations())
    } catch {
      /* a lista é secundária: mantém a anterior */
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    api
      .listConversations()
      .then((list) => !cancelled && setConversations(list))
      .catch(() => undefined)
    return () => {
      cancelled = true
      abortRef.current?.abort()
    }
  }, [])

  const newConversation = useCallback(() => {
    setActiveId(null)
    setMessages([])
    setLoadError(null)
  }, [])

  const openConversation = useCallback(async (id: string) => {
    setLoadError(null)
    try {
      const conv = await api.getConversation(id)
      setActiveId(conv.id)
      setMessages(conv.messages.map((m) => ({ role: m.role, content: m.content, tools: m.tools })))
    } catch (err) {
      setLoadError(errorText(err))
      void refreshConversations()
    }
  }, [refreshConversations])

  const removeConversation = useCallback(
    async (id: string) => {
      try {
        await api.deleteConversation(id)
      } catch (err) {
        // 404: já não existe, então só some da lista.
        if (!(err instanceof ApiError && err.status === 404)) {
          setLoadError(errorText(err))
          return
        }
      }
      if (id === activeId) newConversation()
      await refreshConversations()
    },
    [activeId, newConversation, refreshConversations],
  )

  const send = useCallback(
    async (text: string) => {
      const message = text.trim()
      if (!message || busy) return
      const ctrl = new AbortController()
      abortRef.current = ctrl
      const wasNew = activeId === null
      let convId = activeId
      let streamed = ''
      const tools: ToolCall[] = []
      let final: { content: string; tools: ToolCall[] } | null = null
      let failure: string | null = null

      setLoadError(null)
      setMessages((prev) => [...prev, { role: 'user', content: message, tools: [] }])
      setLive({ text: '', status: THINKING, tools: [] })

      try {
        for await (const ev of streamChat(activeId, message, ctrl.signal)) {
          switch (ev.type) {
            case 'conversation':
              convId = ev.data.id
              setActiveId(convId)
              break
            case 'token':
              streamed += ev.data.text
              setLive({ text: streamed, status: THINKING, tools: [...tools] })
              break
            case 'reset':
              streamed = ''
              setLive({ text: '', status: THINKING, tools: [...tools] })
              break
            case 'tool':
              tools.push(ev.data)
              streamed = ''
              setLive({ text: '', status: `Usando ${ev.data.name}…`, tools: [...tools] })
              break
            case 'answer':
              final = ev.data
              break
            case 'error':
              failure = ev.data.message
              break
            case 'done':
              break
          }
        }
      } catch (err) {
        if (!(err instanceof DOMException && err.name === 'AbortError')) failure = errorText(err)
      }

      setLive(null)
      if (ctrl.signal.aborted) return
      if (failure !== null) {
        setMessages((prev) => [...prev, { role: 'assistant', content: failure, tools: [], error: true }])
        // O turno foi desfeito no servidor: uma conversa nova continua sem existir.
        if (wasNew) setActiveId(null)
      } else if (final) {
        const answer = final
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: answer.content, tools: answer.tools },
        ])
      } else if (streamed) {
        setMessages((prev) => [...prev, { role: 'assistant', content: streamed, tools: tools }])
      }
      if (wasNew || convId) void refreshConversations()
    },
    [activeId, busy, refreshConversations],
  )

  return {
    conversations,
    activeId,
    messages,
    live,
    busy,
    loadError,
    send,
    newConversation,
    openConversation,
    removeConversation,
  }
}
