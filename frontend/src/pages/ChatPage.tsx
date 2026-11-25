import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'
import { api } from '../api/client'
import type { Meta } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { GearIcon, MenuIcon, SendIcon } from '../components/Icons'
import Markdown from '../components/Markdown'
import SettingsDialog from '../components/SettingsDialog'
import Sidebar from '../components/Sidebar'
import ToolsBlock from '../components/ToolsBlock'
import { useChat } from './useChat'
import type { UiMessage } from './useChat'

const SUGGESTIONS = [
  'Qual é a política de reembolso de 2026?',
  'Quantos dias de férias eu tenho?',
  'Quanto está o dólar hoje?',
]

const DESKTOP = '(min-width: 769px)'

function MessageView({ message }: { message: UiMessage }) {
  if (message.role === 'user') {
    return (
      <div className="msg msg-user">
        <p>{message.content}</p>
      </div>
    )
  }
  if (message.error) {
    return (
      <div className="msg msg-error" role="alert">
        {message.content}
      </div>
    )
  }
  return (
    <div className="msg msg-assistant">
      <ToolsBlock tools={message.tools} />
      <Markdown text={message.content} />
    </div>
  )
}

export default function ChatPage() {
  const { user, logout } = useAuth()
  const chat = useChat()
  const [meta, setMeta] = useState<Meta | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(() => window.matchMedia(DESKTOP).matches)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [draft, setDraft] = useState('')
  const endRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    api.meta().then(setMeta).catch(() => setMeta(null))
  }, [])

  useEffect(() => {
    if (!draft && inputRef.current) inputRef.current.style.height = 'auto'
  }, [draft])

  const { messages, live, busy } = chat
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' })
  }, [messages, live])

  if (!user) return null
  const firstName = user.name.trim().split(/\s+/)[0] ?? user.name
  const empty = messages.length === 0 && !live

  function closeOnMobile() {
    if (!window.matchMedia(DESKTOP).matches) setSidebarOpen(false)
  }

  function submit(text: string) {
    const value = text.trim()
    if (!value || busy) return
    setDraft('')
    void chat.send(value)
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      submit(draft)
    }
  }

  function autosize(el: HTMLTextAreaElement) {
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`
  }

  return (
    <div className="layout" data-open={sidebarOpen}>
      <aside className="sidebar" aria-label="Conversas" inert={!sidebarOpen}>
        <Sidebar
          user={user}
          meta={meta}
          conversations={chat.conversations}
          activeId={chat.activeId}
          busy={busy}
          onNew={() => {
            chat.newConversation()
            closeOnMobile()
          }}
          onOpen={(id) => {
            void chat.openConversation(id)
            closeOnMobile()
          }}
          onDelete={chat.removeConversation}
          onLogout={() => void logout()}
        />
      </aside>
      <div className="scrim" onClick={() => setSidebarOpen(false)} aria-hidden="true" />

      <div className="main">
        <header className="topbar">
          <button
            className="icon-btn"
            type="button"
            aria-label={sidebarOpen ? 'Recolher barra lateral' : 'Abrir barra lateral'}
            aria-expanded={sidebarOpen}
            onClick={() => setSidebarOpen((o) => !o)}
          >
            <MenuIcon />
          </button>
          <span className="spacer" />
          {user.is_admin && (
            <button
              className="icon-btn round"
              type="button"
              aria-label="Configurações"
              onClick={() => setSettingsOpen(true)}
            >
              <GearIcon />
            </button>
          )}
        </header>

        <div className="scroll">
          <div className="thread">
            {empty ? (
              <section className="hero">
                <div className="hi">Saudações, {firstName}.</div>
                <div className="ask">Qual sua dúvida hoje?</div>
                <div className="suggestions">
                  {SUGGESTIONS.map((s) => (
                    <button key={s} className="suggestion" type="button" onClick={() => submit(s)}>
                      {s}
                    </button>
                  ))}
                </div>
              </section>
            ) : (
              <div role="log" aria-live="polite" aria-label="Conversa">
                {messages.map((m, i) => (
                  <MessageView key={i} message={m} />
                ))}
                {live && (
                  <div className="msg msg-assistant" aria-busy="true">
                    <ToolsBlock tools={live.tools} />
                    {live.text ? (
                      <div className="streaming">
                        <Markdown text={live.text} />
                        <span className="cursor" aria-hidden="true">
                          ▌
                        </span>
                      </div>
                    ) : (
                      <div className="status" role="status">
                        {live.status}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
            {chat.loadError && (
              <div className="msg msg-error" role="alert">
                {chat.loadError}
              </div>
            )}
            <div ref={endRef} />
          </div>
        </div>

        <footer className="composer-wrap">
          <div className="composer">
            <label htmlFor="composer-input" className="sr-only">
              Mensagem
            </label>
            <textarea
              id="composer-input"
              ref={inputRef}
              rows={1}
              value={draft}
              maxLength={4000}
              placeholder="Pergunte sobre as políticas da empresa"
              onChange={(e) => {
                setDraft(e.target.value)
                autosize(e.target)
              }}
              onKeyDown={onKeyDown}
            />
            <button
              className="send"
              type="button"
              aria-label="Enviar"
              disabled={busy || !draft.trim()}
              onClick={() => submit(draft)}
            >
              <SendIcon />
            </button>
          </div>
          <p className="disclaimer">
            As respostas podem apresentar imprecisões. Considere revisar em fontes confiáveis.
          </p>
        </footer>
      </div>

      {settingsOpen && <SettingsDialog meta={meta} onClose={() => setSettingsOpen(false)} />}
    </div>
  )
}
