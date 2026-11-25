import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../api/client'

type Mode = 'login' | 'register'

type Props = {
  mode: Mode
  onSubmit: (values: { name: string; email: string; password: string }) => Promise<void>
}

type Errors = Partial<Record<'name' | 'email' | 'password', string>>

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

function validate(mode: Mode, name: string, email: string, password: string): Errors {
  const errors: Errors = {}
  if (mode === 'register') {
    const n = name.trim()
    if (n.length < 1 || n.length > 80) errors.name = 'Informe um nome de 1 a 80 caracteres.'
  }
  if (!EMAIL_RE.test(email.trim())) errors.email = 'Informe um e-mail válido.'
  if (mode === 'register') {
    if (password.length < 8 || password.length > 128) {
      errors.password = 'A senha precisa ter de 8 a 128 caracteres.'
    }
  } else if (password.length < 1) {
    errors.password = 'Informe a senha.'
  }
  return errors
}

export default function AuthForm({ mode, onSubmit }: Props) {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [errors, setErrors] = useState<Errors>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const isRegister = mode === 'register'

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const found = validate(mode, name, email, password)
    setErrors(found)
    setFormError(null)
    if (Object.keys(found).length > 0) return
    setBusy(true)
    try {
      await onSubmit({ name: name.trim(), email: email.trim(), password })
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'Algo deu errado. Tente de novo.')
      setBusy(false)
    }
  }

  return (
    <main className="auth-page">
      <form className="auth-card" onSubmit={handleSubmit} noValidate>
        <h1 className="auth-brand">
          <img className="brand-logo" src="/vega-logo.png" alt="" />
          Vega
        </h1>
        {isRegister && <p className="auth-sub">Crie sua conta para começar.</p>}

        {formError && (
          <div className="form-alert" role="alert">
            {formError}
          </div>
        )}

        {isRegister && (
          <div className="field">
            <label htmlFor="name">Nome</label>
            <input
              id="name"
              type="text"
              autoComplete="name"
              maxLength={80}
              value={name}
              onChange={(e) => setName(e.target.value)}
              aria-invalid={!!errors.name}
              aria-describedby={errors.name ? 'name-error' : undefined}
            />
            {errors.name && (
              <span id="name-error" className="field-error">
                {errors.name}
              </span>
            )}
          </div>
        )}

        <div className="field">
          <label htmlFor="email">E-mail</label>
          <input
            id="email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            aria-invalid={!!errors.email}
            aria-describedby={errors.email ? 'email-error' : undefined}
          />
          {errors.email && (
            <span id="email-error" className="field-error">
              {errors.email}
            </span>
          )}
        </div>

        <div className="field">
          <label htmlFor="password">Senha</label>
          <input
            id="password"
            type="password"
            autoComplete={isRegister ? 'new-password' : 'current-password'}
            maxLength={128}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            aria-invalid={!!errors.password}
            aria-describedby={errors.password ? 'password-error' : isRegister ? 'password-hint' : undefined}
          />
          {errors.password ? (
            <span id="password-error" className="field-error">
              {errors.password}
            </span>
          ) : (
            isRegister && (
              <span id="password-hint" className="field-hint">
                Mínimo de 8 caracteres.
              </span>
            )
          )}
        </div>

        <button className="btn btn-primary btn-block" type="submit" disabled={busy}>
          {busy ? 'Aguarde…' : isRegister ? 'Criar conta' : 'Entrar'}
        </button>

        <p className="auth-switch">
          {isRegister ? (
            <>
              Já tem conta? <Link to="/login">Entrar</Link>
            </>
          ) : (
            <>
              Não tem conta? <Link to="/registro">Criar conta</Link>
            </>
          )}
        </p>

        <p className="auth-version">Versão {__APP_VERSION__}</p>
      </form>
    </main>
  )
}
