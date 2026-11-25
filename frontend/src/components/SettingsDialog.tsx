import { useCallback, useEffect, useRef, useState } from 'react'
import type { ChangeEvent, DragEvent } from 'react'
import { api, ApiError } from '../api/client'
import type { DataFile, IngestionResult, Meta, UploadCheck, UploadResult } from '../api/types'
import { UploadIcon, CloseIcon } from './Icons'
import Modal from './Modal'

function errorMessage(err: unknown): string {
  return err instanceof ApiError ? err.message : 'Algo deu errado. Tente de novo.'
}

function extOf(name: string): string {
  const i = name.lastIndexOf('.')
  return i >= 0 ? name.slice(i + 1).toUpperCase() : '—'
}

function formatSize(size: number): string {
  return size < 1024 * 1024 ? `${Math.round(size / 1024)} KB` : `${(size / 1024 / 1024).toFixed(1)} MB`
}

function ingestionText(r: IngestionResult): string {
  return `${r.total} chunks na base: ${r.added} novo(s) ou alterado(s), ${r.deleted} removido(s).`
}

type Feedback = { kind: 'success' | 'error'; text: string }

function FeedbackList({ items }: { items: Feedback[] }) {
  return (
    <>
      {items.map((f, i) => (
        <div key={i} className={`notice notice-${f.kind}`} role={f.kind === 'error' ? 'alert' : 'status'}>
          {f.text}
        </div>
      ))}
    </>
  )
}

function KnowledgeTab({ onChanged, version }: { onChanged: () => void; version: number }) {
  const [files, setFiles] = useState<DataFile[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [feedback, setFeedback] = useState<Feedback[]>([])

  useEffect(() => {
    let cancelled = false
    api
      .listDocuments()
      .then((f) => !cancelled && (setFiles(f), setLoadError(null)))
      .catch((e) => !cancelled && setLoadError(errorMessage(e)))
    return () => {
      cancelled = true
    }
  }, [version])

  async function ingest() {
    setBusy(true)
    setFeedback([])
    try {
      const r = await api.ingest()
      setFeedback([{ kind: 'success', text: ingestionText(r) }])
      onChanged()
    } catch (e) {
      setFeedback([{ kind: 'error', text: `Falha na ingestão: ${errorMessage(e)}` }])
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <p className="dialog-hint">
        Arquivos de <code>data/raw</code> indexados no Astra DB. Gere os embeddings de novo sempre
        que os documentos mudarem.
      </p>
      {loadError && (
        <div className="notice notice-error" role="alert">
          {loadError}
        </div>
      )}
      {files && files.length === 0 && <p className="side-empty">Nenhum arquivo em data/raw.</p>}
      <ul className="file-list">
        {files?.map((f) => (
          <li className="file-row" key={f.name}>
            <span className="file-ext">{extOf(f.name)}</span>
            <span className="file-name">{f.name}</span>
            <span className="file-size">{formatSize(f.size)}</span>
          </li>
        ))}
      </ul>
      <div className="modal-actions left">
        <button
          className="btn btn-primary"
          type="button"
          onClick={ingest}
          disabled={busy || !files || files.length === 0}
        >
          {busy ? 'Indexando…' : 'Gerar embeddings'}
        </button>
      </div>
      <FeedbackList items={feedback} />
    </div>
  )
}

type Pending = { file: File; check: UploadCheck }

function UploadTab({ meta, onUploaded }: { meta: Meta | null; onUploaded: () => void }) {
  const [pending, setPending] = useState<Pending[]>([])
  const [feedback, setFeedback] = useState<Feedback[]>([])
  const [checking, setChecking] = useState(false)
  const [sending, setSending] = useState(false)
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const extensions = meta?.supported_extensions ?? ['.md', '.pdf', '.txt']
  const maxMb = meta?.upload_max_mb ?? 20

  const addFiles = useCallback(async (list: File[]) => {
    if (list.length === 0) return
    setChecking(true)
    setFeedback([])
    try {
      const checks = await api.checkDocuments(list)
      setPending((prev) => {
        const incoming = list.map((file, i) => ({
          file,
          check: checks[i] ?? {
            name: file.name,
            size: file.size,
            ok: false,
            error: 'Não foi possível validar o arquivo.',
            injection_signals: [],
            replaces: false,
          },
        }))
        // Mesmo nome: o mais novo substitui o da lista.
        const names = new Set(incoming.map((p) => p.check.name))
        return [...prev.filter((p) => !names.has(p.check.name)), ...incoming]
      })
    } catch (e) {
      setFeedback([{ kind: 'error', text: errorMessage(e) }])
    } finally {
      setChecking(false)
    }
  }, [])

  function onPick(e: ChangeEvent<HTMLInputElement>) {
    const list = Array.from(e.target.files ?? [])
    e.target.value = ''
    void addFiles(list)
  }

  function onDrop(e: DragEvent) {
    e.preventDefault()
    setDragging(false)
    void addFiles(Array.from(e.dataTransfer.files))
  }

  const valid = pending.filter((p) => p.check.ok)

  async function send() {
    setSending(true)
    setFeedback([])
    try {
      const r: UploadResult = await api.uploadDocuments(valid.map((p) => p.file))
      const items: Feedback[] = []
      if (r.saved.length) {
        items.push({ kind: 'success', text: `Salvo(s): ${r.saved.join(', ')}.` })
      }
      for (const err of r.errors) {
        items.push({ kind: 'error', text: `${err.name}: ${err.message}` })
      }
      if (r.ingestion) items.push({ kind: 'success', text: ingestionText(r.ingestion) })
      if (r.ingestion_error) {
        items.push({
          kind: 'error',
          text: `Os arquivos foram salvos, mas a indexação falhou: ${r.ingestion_error} Tente de novo em "Gerar embeddings".`,
        })
      }
      setFeedback(items)
      setPending([])
      if (r.saved.length) onUploaded()
    } catch (e) {
      setFeedback([{ kind: 'error', text: errorMessage(e) }])
    } finally {
      setSending(false)
    }
  }

  return (
    <div>
      <p className="dialog-hint">
        Aceita {extensions.join(', ')} de até {maxMb} MB. Os válidos são salvos em{' '}
        <code>data/raw</code> e a base é indexada na hora.
      </p>
      <div
        className={`dropzone${dragging ? ' dragging' : ''}`}
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <UploadIcon />
        <span>Solte os arquivos aqui ou</span>
        <button
          className="btn"
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={checking || sending}
        >
          {checking ? 'Validando…' : 'Escolher arquivos'}
        </button>
        <input
          ref={inputRef}
          type="file"
          multiple
          hidden
          accept={extensions.join(',')}
          onChange={onPick}
          aria-label="Escolher arquivos para enviar"
        />
      </div>

      {pending.length > 0 && (
        <ul className="file-list pending">
          {pending.map((p) => {
            const c = p.check
            const tone = !c.ok ? 'bad' : c.injection_signals.length || c.replaces ? 'warn' : ''
            const status = !c.ok
              ? `Recusado: ${c.error ?? 'arquivo inválido.'}`
              : c.injection_signals.length
                ? 'Texto com cara de instrução. Revise antes de enviar.'
                : c.replaces
                  ? 'Substitui o arquivo existente.'
                  : 'Pronto para enviar.'
            return (
              <li className="file-row" key={c.name}>
                <span className="file-ext">{extOf(c.name)}</span>
                <span className="file-info">
                  <span className="file-name">{c.name}</span>
                  <span className={`file-status ${tone}`}>
                    {formatSize(c.size)} · {status}
                    {c.ok && c.injection_signals.length > 0 && c.replaces
                      ? ' Também substitui o arquivo existente.'
                      : ''}
                  </span>
                </span>
                <button
                  className="icon-btn"
                  type="button"
                  aria-label={`Tirar ${c.name} da lista`}
                  onClick={() => setPending((prev) => prev.filter((x) => x !== p))}
                  disabled={sending}
                >
                  <CloseIcon />
                </button>
              </li>
            )
          })}
        </ul>
      )}

      <div className="modal-actions left">
        <button
          className="btn btn-primary"
          type="button"
          onClick={send}
          disabled={valid.length === 0 || sending}
        >
          {sending ? 'Enviando e indexando…' : `Enviar ${valid.length} arquivo(s)`}
        </button>
      </div>
      <FeedbackList items={feedback} />
    </div>
  )
}

export default function SettingsDialog({ meta, onClose }: { meta: Meta | null; onClose: () => void }) {
  const [tab, setTab] = useState<'knowledge' | 'upload'>('knowledge')
  const [version, setVersion] = useState(0)
  const refresh = useCallback(() => setVersion((v) => v + 1), [])

  return (
    <Modal title="Configurações" onClose={onClose}>
      <div className="tabs" role="tablist" aria-label="Configurações">
        <button
          role="tab"
          type="button"
          id="tab-knowledge"
          aria-selected={tab === 'knowledge'}
          aria-controls="panel-knowledge"
          className={tab === 'knowledge' ? 'tab active' : 'tab'}
          onClick={() => setTab('knowledge')}
        >
          Base de conhecimento
        </button>
        <button
          role="tab"
          type="button"
          id="tab-upload"
          aria-selected={tab === 'upload'}
          aria-controls="panel-upload"
          className={tab === 'upload' ? 'tab active' : 'tab'}
          onClick={() => setTab('upload')}
        >
          Adicionar arquivos
        </button>
      </div>
      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === 'knowledge' ? (
          <KnowledgeTab onChanged={refresh} version={version} />
        ) : (
          <UploadTab meta={meta} onUploaded={refresh} />
        )}
      </div>
    </Modal>
  )
}
