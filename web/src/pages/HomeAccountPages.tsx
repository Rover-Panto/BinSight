import {
  ArrowRight,
  Banknote,
  Bell,
  CalendarDays,
  Check,
  ChevronRight,
  CreditCard,
  FlaskConical,
  History,
  Landmark,
  LocateFixed,
  LogOut,
  Mail,
  MapPin,
  PackageSearch,
  Plus,
  Recycle,
  RotateCcw,
  Search,
  ShieldCheck,
  Smartphone,
  Trash2,
  TriangleAlert,
  WalletCards,
} from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Field, InlineNotice, Modal, PageHeading, SectionHeading, StatusBadge } from '../components/UI'
import { formatDateTime, formatMoney, getSessionTotal, rejectedReasons, type MethodType } from '../model'
import { useStore } from '../store'

export function HomePage() {
  const { data, createReturn } = useStore()
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const activeReport = data.reports.find((report) => report.status !== 'Resolved')
  const recentReturn = data.returns[0]

  const startReturn = () => navigate(`/return/${createReturn()}`)
  const search = (event: React.FormEvent) => {
    event.preventDefault()
    navigate(`/guide?q=${encodeURIComponent(query)}`)
  }

  return (
    <div className="page-stack home-page">
      <PageHeading
        eyebrow="Monday, 17 August"
        title="Good afternoon"
        description="Your next services, return activity and local waste updates in one place."
        actions={<StatusBadge tone="info"><span className="live-dot" /> District services online</StatusBadge>}
      />

      <section className="home-lead-grid">
        <div className="return-command">
          <div className="command-index">RETURN / 20 SEN</div>
          <Recycle aria-hidden="true" />
          <div>
            <span className="eyebrow inverse">Beverage return</span>
            <h2>Return cans and bottles</h2>
            <p>Each accepted container adds RM0.20 to your simulated payout.</p>
          </div>
          <button className="button light" type="button" onClick={startReturn}>Start return <ArrowRight aria-hidden="true" /></button>
          <div className="command-lines" aria-hidden="true"><i /><i /><i /></div>
        </div>

        <div className="next-collection surface-panel">
          <div className="panel-kicker"><CalendarDays aria-hidden="true" /><span>Next collection</span><strong>2 days</strong></div>
          <h2>Recycling · Thursday</h2>
          <p>Place clean, dry items at the collection point before 7:00 AM.</p>
          <div className="collection-strip">
            <span><i className="bin-swatch general" /> Garbage <strong>Wed</strong></span>
            <span><i className="bin-swatch recycle" /> Recycling <strong>Thu</strong></span>
            <span><i className="bin-swatch organic" /> Organic <strong>Sat</strong></span>
          </div>
          <Link className="text-link" to="/schedule">View full schedule <ArrowRight aria-hidden="true" /></Link>
        </div>
      </section>

      <section className="service-alert" aria-label="Service alert">
        <TriangleAlert aria-hidden="true" />
        <div><strong>Recycling collection begins earlier this Thursday</strong><span>Set bins out by 7:00 AM due to scheduled road maintenance.</span></div>
        <Link to="/notifications">Details <ChevronRight aria-hidden="true" /></Link>
      </section>

      <section>
        <SectionHeading title="What do you need to do?" detail="Direct access to the most common resident services." />
        <div className="action-rows">
          <Link to="/report" className="action-row danger-accent"><span className="action-icon"><TriangleAlert /></span><span><strong>Report a waste issue</strong><small>Overflow, illegal dumping, missed collection or damaged bins</small></span><ArrowRight /></Link>
          <form className="disposal-search" onSubmit={search}>
            <Search aria-hidden="true" />
            <label htmlFor="home-disposal-search"><strong>How do I dispose of this?</strong><span>Search cans, batteries, electronics and more</span></label>
            <input id="home-disposal-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search an item" />
            <button className="icon-button dark" type="submit" aria-label="Search sorting guide"><ArrowRight /></button>
          </form>
        </div>
      </section>

      <section className="dashboard-columns">
        <div>
          <SectionHeading title="Open report" action={<Link className="text-link" to="/reports">All reports</Link>} />
          {activeReport ? (
            <Link className="report-row" to={`/reports/${activeReport.id}`}>
              <span className="reference-box">{activeReport.id}</span>
              <span><strong>{activeReport.category}</strong><small>{activeReport.location}</small></span>
              <StatusBadge tone="warning">{activeReport.status}</StatusBadge>
              <ChevronRight aria-hidden="true" />
            </Link>
          ) : <p className="muted">No open reports.</p>}
        </div>
        <div>
          <SectionHeading title="Recent return" action={<Link className="text-link" to="/history">History</Link>} />
          {recentReturn && (
            <Link className="return-row" to={`/return/${recentReturn.id}`}>
              <span className="return-symbol"><Recycle /></span>
              <span><strong>{recentReturn.id}</strong><small>{recentReturn.events.filter((event) => event.result === 'accepted').length} items · {formatDateTime(recentReturn.createdAt)}</small></span>
              <strong className="mono amount">{formatMoney(getSessionTotal(recentReturn))}</strong>
              <ChevronRight aria-hidden="true" />
            </Link>
          )}
        </div>
      </section>

      <section className="nearby-strip">
        <div className="mini-map" aria-hidden="true"><i className="road road-one" /><i className="road road-two" /><span className="map-pin primary"><MapPin /></span><span className="map-pin secondary"><Recycle /></span></div>
        <div><span className="eyebrow">Nearest return point · 0.8 km</span><h2>BinSight Central Return Point</h2><p>Open today until 10:00 PM · Cans and plastic bottles</p></div>
        <Link className="button secondary" to="/locations">View locations <LocateFixed /></Link>
      </section>
    </div>
  )
}

export function NotificationsPage() {
  const { data, markNotificationRead, markAllNotificationsRead } = useStore()
  return (
    <div className="page-stack narrow-page">
      <PageHeading title="Notifications" description="Payout confirmations, report progress and local service alerts." actions={<button className="button secondary" type="button" onClick={markAllNotificationsRead}><Check /> Mark all read</button>} />
      <div className="list-panel notification-list">
        {data.notifications.map((note) => (
          <button key={note.id} type="button" className={`notification-row ${note.read ? '' : 'unread'}`} onClick={() => markNotificationRead(note.id)}>
            <span className={`notification-kind ${note.kind}`}>{note.kind === 'payout' ? <Banknote /> : note.kind === 'report' ? <TriangleAlert /> : <Bell />}</span>
            <span><strong>{note.title}</strong><small>{note.detail}</small><time>{formatDateTime(note.createdAt)}</time></span>
            {!note.read && <i aria-label="Unread" />}
          </button>
        ))}
      </div>
    </div>
  )
}

export function AccountPage() {
  const { data, logout, resetDemo, updateSettings } = useStore()
  const navigate = useNavigate()
  const [confirmReset, setConfirmReset] = useState(false)

  return (
    <div className="page-stack narrow-page">
      <PageHeading title="Account" description="Manage your demonstration profile, preferences and payment methods." />
      <section className="profile-summary">
        <span className="large-monogram">MB</span>
        <div><span className="eyebrow">Demonstration resident</span><h2>MON BLUE Tester</h2><p className="mono">ID / {data.auth.userId}</p></div>
        <StatusBadge tone="success"><ShieldCheck /> Verified mock account</StatusBadge>
      </section>

      <section>
        <SectionHeading title="Account services" />
        <div className="settings-list">
          <Link to="/payout-methods"><WalletCards /><span><strong>Payout methods</strong><small>{data.payoutMethods.length} saved methods</small></span><ChevronRight /></Link>
          <Link to="/history"><History /><span><strong>Activity history</strong><small>Returns, payouts and issue reports</small></span><ChevronRight /></Link>
          <Link to="/faq"><PackageSearch /><span><strong>Help and FAQ</strong><small>Find answers about BinSight services</small></span><ChevronRight /></Link>
          <Link to="/contact"><Mail /><span><strong>Contact support</strong><small>Fictional demonstration contacts</small></span><ChevronRight /></Link>
        </div>
      </section>

      <section>
        <SectionHeading title="Notifications" />
        <div className="preference-panel">
          <label><span><strong>Collection reminders</strong><small>Receive a mock reminder before collection day.</small></span><input type="checkbox" checked={data.settings.reminders} onChange={(event) => updateSettings({ reminders: event.target.checked })} /><i /></label>
          <label><span><strong>Service alerts</strong><small>Changes to schedules and local facilities.</small></span><input type="checkbox" checked={data.settings.serviceAlerts} onChange={(event) => updateSettings({ serviceAlerts: event.target.checked })} /><i /></label>
        </div>
      </section>

      <details className="demo-controls">
        <summary><FlaskConical /> Demo controls <span>For prototype testing only</span><ChevronRight /></summary>
        <div>
          <InlineNotice title="Controlled simulation">These options make return and payment states predictable during a presentation.</InlineNotice>
          <Field label="Next return item result">
            <select value={data.settings.nextItemOutcome} onChange={(event) => updateSettings({ nextItemOutcome: event.target.value as 'accepted' | 'rejected' })}>
              <option value="accepted">Accepted</option>
              <option value="rejected">Rejected</option>
            </select>
          </Field>
          {data.settings.nextItemOutcome === 'rejected' && (
            <Field label="Rejection reason">
              <select value={data.settings.rejectedReason} onChange={(event) => updateSettings({ rejectedReason: event.target.value })}>
                {rejectedReasons.map((reason) => <option key={reason}>{reason}</option>)}
              </select>
            </Field>
          )}
          <label className="check-row"><input type="checkbox" checked={data.settings.failNextPayment} onChange={(event) => updateSettings({ failNextPayment: event.target.checked })} /><span><strong>Fail the next payment</strong><small>The setting clears after one attempt.</small></span></label>
        </div>
      </details>

      <section className="account-actions">
        <button className="button secondary" type="button" onClick={() => setConfirmReset(true)}><RotateCcw /> Reset demo data</button>
        <button className="button danger" type="button" onClick={() => { logout(); navigate('/login') }}><LogOut /> Sign out</button>
      </section>
      {confirmReset && (
        <Modal title="Reset demonstration data?" description="This restores the original sessions, reports, methods and settings." onClose={() => setConfirmReset(false)}>
          <div className="modal-actions"><button className="button ghost" type="button" onClick={() => setConfirmReset(false)}>Cancel</button><button className="button danger" type="button" onClick={() => { resetDemo(); setConfirmReset(false) }}><RotateCcw /> Reset data</button></div>
        </Modal>
      )}
    </div>
  )
}

export function PayoutMethodsPage() {
  const { data, addPayoutMethod, removePayoutMethod, setDefaultMethod } = useStore()
  const [adding, setAdding] = useState(false)
  const [removing, setRemoving] = useState<string | null>(null)
  const [type, setType] = useState<MethodType>('bank')
  const [identifier, setIdentifier] = useState('')
  const [error, setError] = useState('')
  const pendingRemoval = data.payoutMethods.find((method) => method.id === removing)

  const submit = (event: React.FormEvent) => {
    event.preventDefault()
    const digits = identifier.replace(/\D/g, '')
    if (digits.length < 4) { setError('Enter at least four fictional digits.'); return }
    addPayoutMethod(type, digits.slice(-4))
    setIdentifier('')
    setAdding(false)
  }

  return (
    <div className="page-stack narrow-page">
      <PageHeading title="Payout methods" description="Only masked demonstration identifiers are saved." actions={<button className="button primary" type="button" onClick={() => setAdding(true)}><Plus /> Add method</button>} />
      <InlineNotice title="Use fictional details only">Complete bank-account and wallet information is never retained by this prototype.</InlineNotice>
      <div className="payment-method-list">
        {data.payoutMethods.map((method) => (
          <article key={method.id} className="payment-method-row">
            <span className="method-icon">{method.type === 'bank' ? <Landmark /> : <Smartphone />}</span>
            <span><strong>{method.label}</strong><small className="mono">{method.maskedIdentifier}</small></span>
            {method.isDefault ? <StatusBadge tone="success">Default</StatusBadge> : <button className="text-button" type="button" onClick={() => setDefaultMethod(method.id)}>Set default</button>}
            <button className="icon-button danger-icon" type="button" onClick={() => setRemoving(method.id)} aria-label={`Remove ${method.maskedIdentifier}`}><Trash2 /></button>
          </article>
        ))}
        {data.payoutMethods.length === 0 && <InlineNotice tone="warning" title="No payout method saved">Add a Bank Transfer or E-Wallet method before completing a return.</InlineNotice>}
      </div>
      {adding && (
        <Modal title="Add payout method" description="The prototype will keep only the final four digits." onClose={() => setAdding(false)}>
          <form className="stacked-form" onSubmit={submit}>
            <div className="segmented-control" role="radiogroup" aria-label="Payout type">
              <label><input type="radio" name="method-type" value="bank" checked={type === 'bank'} onChange={() => setType('bank')} /><span><Landmark /> Bank Transfer</span></label>
              <label><input type="radio" name="method-type" value="wallet" checked={type === 'wallet'} onChange={() => setType('wallet')} /><span><Smartphone /> E-Wallet</span></label>
            </div>
            <Field label={type === 'bank' ? 'Demonstration account number' : 'Demonstration wallet number'} hint="Do not enter real financial details." error={error}>
              <div className="input-with-icon"><CreditCard /><input inputMode="numeric" value={identifier} onChange={(event) => { setIdentifier(event.target.value); setError('') }} placeholder="0000 0000" /></div>
            </Field>
            <div className="modal-actions"><button className="button ghost" type="button" onClick={() => setAdding(false)}>Cancel</button><button className="button primary" type="submit"><Plus /> Add method</button></div>
          </form>
        </Modal>
      )}
      {pendingRemoval && (
        <Modal title="Remove payout method?" description={pendingRemoval.maskedIdentifier} onClose={() => setRemoving(null)}>
          <div className="modal-actions"><button className="button ghost" type="button" onClick={() => setRemoving(null)}>Cancel</button><button className="button danger" type="button" onClick={() => { removePayoutMethod(pendingRemoval.id); setRemoving(null) }}><Trash2 /> Remove</button></div>
        </Modal>
      )}
    </div>
  )
}

export function HistoryPage() {
  const { data } = useStore()
  const activities = [
    ...data.returns.map((session) => ({ type: 'Return', id: session.id, date: session.createdAt, title: `${session.events.filter((event) => event.result === 'accepted').length} accepted items`, value: formatMoney(getSessionTotal(session)), to: `/return/${session.id}`, icon: Recycle })),
    ...data.reports.map((report) => ({ type: 'Report', id: report.id, date: report.createdAt, title: report.category, value: report.status, to: `/reports/${report.id}`, icon: TriangleAlert })),
  ].sort((a, b) => +new Date(b.date) - +new Date(a.date))

  return (
    <div className="page-stack narrow-page">
      <PageHeading title="Activity history" description="Return sessions, simulated payouts and waste reports." />
      <div className="activity-list">
        {activities.map((activity) => {
          const Icon = activity.icon
          return <Link key={`${activity.type}-${activity.id}`} to={activity.to}><span className="activity-icon"><Icon /></span><span><small>{activity.type} · {activity.id}</small><strong>{activity.title}</strong><time>{formatDateTime(activity.date)}</time></span><span className="activity-value">{activity.value}</span><ChevronRight /></Link>
        })}
      </div>
    </div>
  )
}
