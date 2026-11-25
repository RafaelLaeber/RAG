import { useState } from 'react'
import type { ConversationSummary, Meta, User } from '../api/types'
import { PlusIcon, TrashIcon } from './Icons'
import Modal from './Modal'

type Props = {
  user: User
  meta: Meta | null
  conversations: ConversationSummary[]
  activeId: string | null
  busy: boolean
  onNew: () => void
  onOpen: (id: string) => void
  onDelete: (id: string) => Promise<void>
  onLogout: () => void
}

export default function Sidebar({
  user,
  meta,
  conversations,
  activeId,
  busy,
  onNew,
  onOpen,
  onDelete,
  onLogout,
}: Props) {
  const [target, setTarget] = useState<ConversationSummary | null>(null)
  const [deleting, setDeleting] = useState(false)

  async function confirmDelete() {
    if (!target) return
    setDeleting(true)
    try {
      await onDelete(target.id)
    } finally {
      setDeleting(false)
      setTarget(null)
    }
  }

  return (
    <>
      <div className="side-title">
        <img className="brand-logo" src="/vega-logo.png" alt="" />
        Vega
      </div>
      <div className="side-pad">
        <button className="btn btn-primary btn-block" type="button" onClick={onNew} disabled={busy}>
          <PlusIcon /> Nova conversa
        </button>
      </div>

      <div className="side-label" id="recent-label">
        Conversas recentes
      </div>
      <nav className="conv-list" aria-labelledby="recent-label">
        {conversations.length === 0 && <p className="side-empty">Nenhuma conversa ainda.</p>}
        {conversations.map((c) => (
          <div className={`conv-row${c.id === activeId ? ' active' : ''}`} key={c.id}>
            <button
              className="conv-btn"
              type="button"
              title={`${c.title} — ${new Date(c.updated_at).toLocaleString('pt-BR')}`}
              aria-current={c.id === activeId ? 'true' : undefined}
              disabled={busy}
              onClick={() => onOpen(c.id)}
            >
              {c.title}
            </button>
            <button
              className="icon-btn conv-del"
              type="button"
              aria-label={`Apagar conversa ${c.title}`}
              disabled={busy}
              onClick={() => setTarget(c)}
            >
              <TrashIcon />
            </button>
          </div>
        ))}
      </nav>

      <div className="side-foot">
        <div className="side-user">
          <span className="side-user-name">{user.name}</span>
          <span className="side-user-email">{user.email}</span>
        </div>
        <button className="btn btn-block" type="button" onClick={onLogout}>
          Sair
        </button>
      </div>

      {target && (
        <Modal title="Apagar conversa?" size="small" onClose={() => !deleting && setTarget(null)}>
          <p className="dialog-hint">
            A conversa <b>{target.title}</b> e todas as mensagens dela serão apagadas. Essa ação não
            pode ser desfeita.
          </p>
          <div className="modal-actions">
            <button className="btn" type="button" onClick={() => setTarget(null)} disabled={deleting}>
              Cancelar
            </button>
            <button
              className="btn btn-danger"
              type="button"
              onClick={confirmDelete}
              disabled={deleting}
            >
              {deleting ? 'Apagando…' : 'Apagar'}
            </button>
          </div>
        </Modal>
      )}
    </>
  )
}
