import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { api, ApiError } from '../api/client'
import type { User, UserUpdate } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { EditIcon, PlusIcon, TrashIcon } from './Icons'
import Modal from './Modal'

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
// Acima disso a lista ganha rolagem (mesma altura da lista de documentos)
const MAX_VISIBLE_USERS = 6

function errorMessage(err: unknown): string {
  return err instanceof ApiError ? err.message : 'Algo deu errado. Tente de novo.'
}

type Errors = Partial<Record<'name' | 'email' | 'password', string>>

/** Mesmas regras da API (schemas.py). Na edição, senha vazia mantém a atual. */
function validate(name: string, email: string, password: string, editing: boolean): Errors {
  const errors: Errors = {}
  const n = name.trim()
  if (n.length < 1 || n.length > 80) errors.name = 'Informe um nome de 1 a 80 caracteres.'
  if (!EMAIL_RE.test(email.trim())) errors.email = 'Informe um e-mail válido.'
  if (!(editing && password === '') && (password.length < 8 || password.length > 128)) {
    errors.password = 'A senha precisa ter de 8 a 128 caracteres.'
  }
  return errors
}

type FormProps = {
  /** null = criar usuário novo. */
  user: User | null
  isSelf: boolean
  onClose: () => void
  onSaved: (user: User) => void
}

function UserForm({ user, isSelf, onClose, onSaved }: FormProps) {
  const editing = user !== null
  const [name, setName] = useState(user?.name ?? '')
  const [email, setEmail] = useState(user?.email ?? '')
  const [password, setPassword] = useState('')
  const [isAdmin, setIsAdmin] = useState(user?.is_admin ?? false)
  const [errors, setErrors] = useState<Errors>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    const found = validate(name, email, password, editing)
    setErrors(found)
    setFormError(null)
    if (Object.keys(found).length > 0) return
    setBusy(true)
    try {
      let saved: User
      if (user) {
        // Manda só o que mudou
        const body: UserUpdate = {}
        if (name.trim() !== user.name) body.name = name.trim()
        if (email.trim().toLowerCase() !== user.email) body.email = email.trim()
        if (password) body.password = password
        if (isAdmin !== user.is_admin) body.is_admin = isAdmin
        saved = Object.keys(body).length ? await api.updateUser(user.id, body) : user
      } else {
        saved = await api.createUser({ name: name.trim(), email: email.trim(), password, is_admin: isAdmin })
      }
      onSaved(saved)
    } catch (err) {
      setFormError(errorMessage(err))
      setBusy(false)
    }
  }

  return (
    <Modal title={editing ? 'Editar usuário' : 'Novo usuário'} size="small" onClose={() => !busy && onClose()}>
      <form className="user-form" onSubmit={submit} noValidate>
        {formError && (
          <div className="form-alert" role="alert">
            {formError}
          </div>
        )}
        <div className="field">
          <label htmlFor="user-name">Nome</label>
          <input
            id="user-name"
            type="text"
            maxLength={80}
            value={name}
            onChange={(e) => setName(e.target.value)}
            aria-invalid={!!errors.name}
            aria-describedby={errors.name ? 'user-name-error' : undefined}
          />
          {errors.name && (
            <span id="user-name-error" className="field-error">
              {errors.name}
            </span>
          )}
        </div>
        <div className="field">
          <label htmlFor="user-email">E-mail</label>
          <input
            id="user-email"
            type="email"
            autoComplete="off"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            aria-invalid={!!errors.email}
            aria-describedby={errors.email ? 'user-email-error' : undefined}
          />
          {errors.email && (
            <span id="user-email-error" className="field-error">
              {errors.email}
            </span>
          )}
        </div>
        <div className="field">
          <label htmlFor="user-password">{editing ? 'Nova senha' : 'Senha'}</label>
          <input
            id="user-password"
            type="password"
            autoComplete="new-password"
            maxLength={128}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            aria-invalid={!!errors.password}
            aria-describedby={errors.password ? 'user-password-error' : 'user-password-hint'}
          />
          {errors.password ? (
            <span id="user-password-error" className="field-error">
              {errors.password}
            </span>
          ) : (
            <span id="user-password-hint" className="field-hint">
              {editing
                ? 'Deixe em branco para manter a atual. Trocar a senha encerra as sessões abertas do usuário.'
                : 'Mínimo de 8 caracteres.'}
            </span>
          )}
        </div>
        <label className="check">
          <input
            type="checkbox"
            checked={isAdmin}
            onChange={(e) => setIsAdmin(e.target.checked)}
            disabled={isSelf}
          />
          <span>
            Administrador
            <span className="field-hint">
              {isSelf
                ? 'Você não pode tirar o seu próprio acesso.'
                : 'Gerencia a base de conhecimento e os usuários.'}
            </span>
          </span>
        </label>
        <div className="modal-actions">
          <button className="btn" type="button" onClick={onClose} disabled={busy}>
            Cancelar
          </button>
          <button className="btn btn-primary" type="submit" disabled={busy}>
            {busy ? 'Salvando…' : editing ? 'Salvar' : 'Criar usuário'}
          </button>
        </div>
      </form>
    </Modal>
  )
}

type Feedback = { kind: 'success' | 'error'; text: string }

export default function UsersTab() {
  const { user: me, setCurrentUser } = useAuth()
  const [users, setUsers] = useState<User[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [version, setVersion] = useState(0)
  const [feedback, setFeedback] = useState<Feedback | null>(null)
  // undefined = formulário fechado; null = novo usuário
  const [editing, setEditing] = useState<User | null | undefined>(undefined)
  const [target, setTarget] = useState<User | null>(null)
  const [deleting, setDeleting] = useState(false)

  useEffect(() => {
    let cancelled = false
    api
      .listUsers()
      .then((u) => !cancelled && (setUsers(u), setLoadError(null)))
      .catch((e) => !cancelled && setLoadError(errorMessage(e)))
    return () => {
      cancelled = true
    }
  }, [version])

  function onSaved(saved: User) {
    const created = editing === null
    setEditing(undefined)
    setFeedback({ kind: 'success', text: created ? `${saved.name} criado.` : `${saved.name} atualizado.` })
    if (saved.id === me?.id) setCurrentUser(saved)
    setVersion((v) => v + 1)
  }

  async function confirmDelete() {
    if (!target) return
    setDeleting(true)
    setFeedback(null)
    try {
      await api.deleteUser(target.id)
      setFeedback({ kind: 'success', text: `${target.name} apagado.` })
      setVersion((v) => v + 1)
    } catch (e) {
      setFeedback({ kind: 'error', text: `Falha ao apagar: ${errorMessage(e)}` })
    } finally {
      setDeleting(false)
      setTarget(null)
    }
  }

  return (
    <div>
      <p className="dialog-hint">
        Contas com acesso ao Vega. Apagar um usuário apaga também as conversas e as memórias dele.
      </p>
      {loadError && (
        <div className="notice notice-error" role="alert">
          {loadError}
        </div>
      )}
      <ul className={`file-list users${users && users.length > MAX_VISIBLE_USERS ? ' scroll' : ''}`}>
        {users?.map((u) => {
          const isSelf = u.id === me?.id
          return (
            <li className="file-row" key={u.id}>
              <span className="file-info">
                <span className="file-name">
                  {u.name}
                  {isSelf && <span className="user-self"> (você)</span>}
                </span>
                <span className="file-status">{u.email}</span>
              </span>
              {u.is_admin && <span className="user-badge">Admin</span>}
              <button
                className="icon-btn file-del row-edit"
                type="button"
                aria-label={`Editar ${u.name}`}
                onClick={() => setEditing(u)}
              >
                <EditIcon />
              </button>
              {isSelf ? (
                // Ocupa o lugar da lixeira para os selos e os lápis ficarem alinhados
                <span className="row-spacer" aria-hidden="true" />
              ) : (
                <button
                  className="icon-btn file-del"
                  type="button"
                  aria-label={`Apagar ${u.name}`}
                  onClick={() => setTarget(u)}
                >
                  <TrashIcon />
                </button>
              )}
            </li>
          )
        })}
      </ul>
      <div className="modal-actions left">
        <button className="btn btn-primary btn-icon" type="button" onClick={() => setEditing(null)}>
          <PlusIcon />
          Novo usuário
        </button>
      </div>
      {feedback && (
        <div
          className={`notice notice-${feedback.kind}`}
          role={feedback.kind === 'error' ? 'alert' : 'status'}
        >
          {feedback.text}
        </div>
      )}

      {editing !== undefined && (
        <UserForm
          user={editing}
          isSelf={editing?.id === me?.id}
          onClose={() => setEditing(undefined)}
          onSaved={onSaved}
        />
      )}

      {target && (
        <Modal title="Apagar usuário?" size="small" onClose={() => !deleting && setTarget(null)}>
          <p className="dialog-hint">
            A conta de <b>{target.name}</b> ({target.email}), as conversas e as memórias dela serão
            apagadas. Essa ação não pode ser desfeita.
          </p>
          <div className="modal-actions">
            <button className="btn" type="button" onClick={() => setTarget(null)} disabled={deleting}>
              Cancelar
            </button>
            <button className="btn btn-danger" type="button" onClick={confirmDelete} disabled={deleting}>
              {deleting ? 'Apagando…' : 'Apagar'}
            </button>
          </div>
        </Modal>
      )}
    </div>
  )
}
