import { Check, CircleAlert, Info, X } from 'lucide-react'
import { useEffect, type ReactNode } from 'react'

export function PageHeading({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string
  title: string
  description?: string
  actions?: ReactNode
}) {
  return (
    <header className="page-heading">
      <div>
        {eyebrow && <span className="eyebrow">{eyebrow}</span>}
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </header>
  )
}

export function SectionHeading({
  title,
  detail,
  action,
}: {
  title: string
  detail?: string
  action?: ReactNode
}) {
  return (
    <div className="section-heading">
      <div><h2>{title}</h2>{detail && <p>{detail}</p>}</div>
      {action}
    </div>
  )
}

export function StatusBadge({
  tone,
  children,
}: {
  tone: 'success' | 'warning' | 'danger' | 'info' | 'neutral'
  children: ReactNode
}) {
  return <span className={`status-badge ${tone}`}>{children}</span>
}

export function InlineNotice({
  tone = 'info',
  title,
  children,
}: {
  tone?: 'info' | 'success' | 'warning' | 'danger'
  title: string
  children: ReactNode
}) {
  const Icon = tone === 'success' ? Check : tone === 'info' ? Info : CircleAlert
  return (
    <div className={`inline-notice ${tone}`} role={tone === 'danger' ? 'alert' : 'status'}>
      <Icon aria-hidden="true" />
      <div><strong>{title}</strong><p>{children}</p></div>
    </div>
  )
}

export function Modal({
  title,
  description,
  children,
  onClose,
}: {
  title: string
  description?: string
  children: ReactNode
  onClose: () => void
}) {
  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', closeOnEscape)
    return () => document.removeEventListener('keydown', closeOnEscape)
  }, [onClose])

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.currentTarget === event.target && onClose()}>
      <section className="modal-panel" role="dialog" aria-modal="true" aria-labelledby="modal-title">
        <header>
          <div><h2 id="modal-title">{title}</h2>{description && <p>{description}</p>}</div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Close dialog"><X aria-hidden="true" /></button>
        </header>
        {children}
      </section>
    </div>
  )
}

export function EmptyState({
  icon,
  title,
  detail,
  action,
}: {
  icon: ReactNode
  title: string
  detail: string
  action?: ReactNode
}) {
  return (
    <div className="empty-state">
      <span className="empty-icon">{icon}</span>
      <h3>{title}</h3>
      <p>{detail}</p>
      {action}
    </div>
  )
}

export function Field({ label, hint, error, children }: { label: string; hint?: string; error?: string; children: ReactNode }) {
  return (
    <label className={`field ${error ? 'has-error' : ''}`}>
      <span className="field-label">{label}</span>
      {children}
      {error ? <small className="field-error">{error}</small> : hint ? <small>{hint}</small> : null}
    </label>
  )
}
