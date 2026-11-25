import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { CloseIcon } from './Icons'

type Props = {
  title: string
  onClose: () => void
  children: ReactNode
  size?: 'small' | 'large'
}

/** Modal sobre o <dialog> nativo: foco preso, Esc fecha e o fundo fica inerte. */
export default function Modal({ title, onClose, children, size = 'large' }: Props) {
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const dialog = ref.current
    if (dialog && !dialog.open) dialog.showModal()
  }, [])

  return (
    <dialog
      ref={ref}
      className={`modal modal-${size}`}
      aria-labelledby="modal-title"
      onClose={onClose}
      onClick={(e) => {
        if (e.target === ref.current) onClose()
      }}
    >
      <div className="modal-head">
        <h2 id="modal-title">{title}</h2>
        <button className="icon-btn" type="button" aria-label="Fechar" onClick={onClose}>
          <CloseIcon />
        </button>
      </div>
      <div className="modal-body">{children}</div>
    </dialog>
  )
}
