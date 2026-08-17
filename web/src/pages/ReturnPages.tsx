import {
  ArrowRight,
  BottleWine,
  Check,
  CheckCircle2,
  ChevronRight,
  CreditCard,
  Landmark,
  PackageOpen,
  Plus,
  ReceiptText,
  Recycle,
  Redo2,
  ScanLine,
  ShieldCheck,
  Smartphone,
  X,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom'
import { EmptyState, InlineNotice, PageHeading, SectionHeading, StatusBadge } from '../components/UI'
import { formatDateTime, formatMoney, getSessionTotal } from '../model'
import { useStore } from '../store'

export function ReturnLandingPage() {
  const { data, createReturn } = useStore()
  const navigate = useNavigate()
  const active = data.returns.find((session) => session.status !== 'paid')
  const completed = data.returns.filter((session) => session.status === 'paid').slice(0, 3)

  const begin = () => navigate(`/return/${createReturn()}`)

  return (
    <div className="page-stack">
      <PageHeading eyebrow="20 sen per accepted item" title="Beverage returns" description="Create a simulated session for eligible cans and plastic bottles." actions={<StatusBadge tone="info"><ShieldCheck /> Prototype payout</StatusBadge>} />
      {active ? (
        <section className="resume-session">
          <div><span className="eyebrow inverse">Session in progress</span><h2>{active.id}</h2><p>{active.events.filter((event) => event.result === 'accepted').length} accepted items · {formatMoney(getSessionTotal(active))}</p></div>
          <Link className="button light" to={active.status === 'awaiting-payout' ? `/payout/${active.id}` : `/return/${active.id}`}>Continue session <ArrowRight /></Link>
        </section>
      ) : (
        <section className="return-start-panel">
          <div className="return-machine-visual" aria-hidden="true"><span>BIN / SIGHT</span><div><Recycle /><i /></div><small>READY</small></div>
          <div><span className="eyebrow">Return station simulator</span><h2>Ready to return containers?</h2><p>No camera or QR access is used in this mock-up. Start a session, insert one item at a time, and let the station identify whether it can be accepted.</p><button className="button primary" type="button" onClick={begin}>Start return <ArrowRight /></button></div>
        </section>
      )}
      <section>
        <SectionHeading title="How it works" />
        <ol className="process-steps">
          <li><span>01</span><div><strong>Start a session</strong><p>A return reference is generated on this device.</p></div></li>
          <li><span>02</span><div><strong>Insert one container</strong><p>The station identifies the item and confirms whether it is accepted.</p></div></li>
          <li><span>03</span><div><strong>Choose payout</strong><p>Use a mock Bank Transfer or E-Wallet method.</p></div></li>
        </ol>
      </section>
      <section>
        <SectionHeading title="Recent completed returns" action={<Link className="text-link" to="/history">View all activity</Link>} />
        <div className="compact-table">
          {completed.map((session) => (
            <Link key={session.id} to={`/return/${session.id}`}><span className="mono">{session.id}</span><span>{session.events.filter((event) => event.result === 'accepted').length} items</span><strong>{formatMoney(getSessionTotal(session))}</strong><time>{formatDateTime(session.paidAt ?? session.createdAt)}</time><ChevronRight /></Link>
          ))}
        </div>
      </section>
    </div>
  )
}

export function ReturnSessionPage() {
  const { id } = useParams()
  const { data, addItem, retryItem, finishReturn } = useStore()
  const navigate = useNavigate()
  const [inspecting, setInspecting] = useState(false)
  const session = data.returns.find((entry) => entry.id === id)

  if (!session) return <Navigate to="/return" replace />
  if (session.status === 'awaiting-payout') return <Navigate to={`/payout/${session.id}`} replace />

  const acceptedEvents = session.events.filter((event) => event.result === 'accepted')
  const rejectedEvents = session.events.filter((event) => event.result === 'rejected')
  const latest = session.events.at(-1)
  const canCount = acceptedEvents.filter((event) => event.type === 'Can').length
  const bottleCount = acceptedEvents.filter((event) => event.type === 'Bottle').length
  const total = getSessionTotal(session)
  const recoverable = latest?.result === 'rejected' && latest.reason === 'Barcode could not be read'

  if (session.status === 'paid') {
    const method = data.payoutMethods.find((entry) => entry.id === session.payoutMethodId)
    return (
      <div className="page-stack narrow-page">
        <PageHeading eyebrow="Completed return" title={session.id} description="Simulated transaction receipt" />
        <Receipt sessionId={session.id} total={total} itemCount={acceptedEvents.length} method={method?.maskedIdentifier ?? 'Saved payout method'} transactionId={session.transactionId ?? 'TXN-DEMO'} paidAt={session.paidAt ?? session.createdAt} />
        <div className="center-actions"><Link className="button primary" to="/return">Return another item <Recycle /></Link><Link className="button secondary" to="/history">View activity</Link></div>
      </div>
    )
  }

  const inspectItem = () => {
    if (inspecting) return
    setInspecting(true)
    window.setTimeout(() => {
      addItem(session.id)
      setInspecting(false)
    }, 850)
  }

  const finish = () => {
    if (acceptedEvents.length === 0) return
    finishReturn(session.id)
    navigate(`/payout/${session.id}`)
  }

  return (
    <div className="page-stack return-session-page">
      <PageHeading eyebrow="Active return session" title={session.id} description="Insert one container at a time. The station identifies it before the session is updated." actions={<StatusBadge tone="success"><span className="live-dot" /> Station ready</StatusBadge>} />
      <section className="session-console">
        <div className="session-totals">
          <span><small>Cans</small><strong>{canCount}</strong></span>
          <span><small>Bottles</small><strong>{bottleCount}</strong></span>
          <span><small>Rejected</small><strong>{rejectedEvents.length}</strong></span>
          <span className="payout-total"><small>Current payout</small><strong>{formatMoney(total)}</strong></span>
        </div>
        <div className="session-meter" aria-label={`${acceptedEvents.length} accepted items`}><i style={{ width: `${Math.min(100, acceptedEvents.length * 10)}%` }} /></div>
        <div className="session-rate"><span>RATE / ITEM</span><strong>RM0.20</strong><small>Simulated value</small></div>
      </section>

      {inspecting && (
        <section className="result-panel inspecting" aria-live="polite">
          <span className="result-icon"><ScanLine /></span>
          <div><span className="eyebrow">Inspection in progress</span><h2>Checking the container</h2><p>The station is identifying the item and validating its return eligibility.</p></div>
          <span className="inspection-pulse" aria-hidden="true"><i /><i /><i /></span>
        </section>
      )}

      {!inspecting && latest?.result === 'accepted' && (
        <section className="result-panel accepted" aria-live="polite">
          <span className="result-icon"><Check /></span>
          <div><span className="eyebrow">Item accepted</span><h2>{latest.type} accepted · +RM0.20</h2><p>The container has been added to session {session.id}.</p></div>
          <div className="result-actions"><button className="button primary" type="button" onClick={inspectItem}><Plus /> Add another item</button><button className="button secondary" type="button" onClick={finish}>Finish return</button></div>
        </section>
      )}

      {!inspecting && latest?.result === 'rejected' && (
        <section className="result-panel rejected" aria-live="assertive">
          <span className="result-icon"><X /></span>
          <div><span className="eyebrow">Item not accepted</span><h2>{latest.reason}</h2><p>No item or payout value was added. Remove the container before continuing.</p></div>
          <div className="result-actions"><button className="button primary" type="button" onClick={inspectItem}><Plus /> Add another item</button>{recoverable && <button className="button secondary" type="button" onClick={() => retryItem(session.id, latest.type)}><Redo2 /> Try this item again</button>}{acceptedEvents.length > 0 && <button className="text-button" type="button" onClick={finish}>Finish return</button>}</div>
        </section>
      )}

      {!latest && !inspecting && (
        <EmptyState icon={<PackageOpen />} title="Ready for the first container" detail="Place one container into the return opening. The station will identify it and check eligibility." action={<button className="button primary" type="button" onClick={inspectItem}><Plus /> Add item</button>} />
      )}

      <section>
        <SectionHeading title="Session activity" detail={`${session.events.length} inspection ${session.events.length === 1 ? 'event' : 'events'}`} />
        {session.events.length > 0 ? (
          <div className="event-log">
            {[...session.events].reverse().map((event, index) => (
              <div key={event.id} className={event.result}>
                <span className="event-index">{String(session.events.length - index).padStart(2, '0')}</span>
                <span className="event-type">{event.type === 'Can' ? <Recycle /> : <BottleWine />}</span>
                <span><strong>{event.type}</strong><small>{formatDateTime(event.createdAt)}</small></span>
                <StatusBadge tone={event.result === 'accepted' ? 'success' : 'danger'}>{event.result === 'accepted' ? 'Accepted' : 'Rejected'}</StatusBadge>
                <span className="mono event-value">{event.result === 'accepted' ? '+RM0.20' : 'RM0.00'}</span>
              </div>
            ))}
          </div>
        ) : <p className="muted">Inspection events will appear here.</p>}
      </section>

      <div className="session-sticky-actions">
        <button className="button primary" type="button" onClick={inspectItem} disabled={inspecting}><Plus /> {inspecting ? 'Checking item' : 'Add item'}</button>
        <button className="button secondary" type="button" onClick={finish} disabled={acceptedEvents.length === 0 || inspecting}>Finish return</button>
      </div>
    </div>
  )
}

export function PayoutPage() {
  const { id } = useParams()
  const { data, payReturn } = useStore()
  const session = data.returns.find((entry) => entry.id === id)
  const defaultMethod = data.payoutMethods.find((method) => method.isDefault)?.id ?? data.payoutMethods[0]?.id ?? ''
  const [selectedMethod, setSelectedMethod] = useState(defaultMethod)
  const [processing, setProcessing] = useState(false)
  const [failed, setFailed] = useState(false)
  const [showToast, setShowToast] = useState(false)

  const total = useMemo(() => session ? getSessionTotal(session) : 0, [session])

  useEffect(() => {
    if (!showToast) return
    const timer = window.setTimeout(() => setShowToast(false), 4500)
    return () => window.clearTimeout(timer)
  }, [showToast])

  if (!session) return <Navigate to="/return" replace />
  const selected = data.payoutMethods.find((method) => method.id === selectedMethod)

  if (session.status === 'paid') {
    const method = data.payoutMethods.find((entry) => entry.id === session.payoutMethodId)
    return (
      <div className="page-stack narrow-page">
        <PageHeading eyebrow="Payment complete" title={`${formatMoney(total)} sent`} description="The simulated payout has been recorded." />
        <Receipt sessionId={session.id} total={total} itemCount={session.events.filter((event) => event.result === 'accepted').length} method={method?.maskedIdentifier ?? 'Saved payout method'} transactionId={session.transactionId ?? 'TXN-DEMO'} paidAt={session.paidAt ?? session.createdAt} />
        <div className="center-actions"><Link className="button primary" to="/return">Done <CheckCircle2 /></Link><Link className="button secondary" to="/history">View history</Link></div>
        {showToast && <div className="toast success" role="status"><CheckCircle2 /><span><strong>Money sent</strong>{formatMoney(total)} sent successfully.</span><button className="icon-button" onClick={() => setShowToast(false)} aria-label="Dismiss notification"><X /></button></div>}
      </div>
    )
  }

  const send = () => {
    if (!selectedMethod) return
    setProcessing(true)
    setFailed(false)
    window.setTimeout(() => {
      const result = payReturn(session.id, selectedMethod)
      setProcessing(false)
      if (result.ok) setShowToast(true)
      else setFailed(true)
    }, 1200)
  }

  return (
    <div className="page-stack payout-page">
      <PageHeading eyebrow={`Return ${session.id}`} title="Choose payout method" description="Select where the simulated return value should be sent." />
      <div className="payout-layout">
        <section className="payout-method-panel">
          <SectionHeading title="Saved methods" action={<Link className="text-link" to="/payout-methods"><Plus /> Manage methods</Link>} />
          {data.payoutMethods.length === 0 ? (
            <InlineNotice tone="warning" title="Add a payout method">A Bank Transfer or E-Wallet method is required before continuing.</InlineNotice>
          ) : (
            <div className="payout-choice-list" role="radiogroup" aria-label="Payout method">
              {data.payoutMethods.map((method) => (
                <label key={method.id} className={selectedMethod === method.id ? 'selected' : ''}>
                  <input type="radio" name="payout-method" checked={selectedMethod === method.id} onChange={() => setSelectedMethod(method.id)} />
                  <span className="method-icon">{method.type === 'bank' ? <Landmark /> : <Smartphone />}</span>
                  <span><strong>{method.label}</strong><small className="mono">{method.maskedIdentifier}</small></span>
                  {method.isDefault && <StatusBadge tone="neutral">Default</StatusBadge>}
                  <i><Check /></i>
                </label>
              ))}
            </div>
          )}
          {failed && <InlineNotice tone="danger" title="Payment could not be completed">The simulated transfer failed. Confirm the method and try again.</InlineNotice>}
          <button className="button primary wide payout-button" type="button" onClick={send} disabled={!selectedMethod || processing}>
            {processing ? <><span className="spinner" /> Processing payment</> : <>Send {formatMoney(total)} <ArrowRight /></>}
          </button>
          <div className="secure-note"><ShieldCheck /><span>No real financial transaction will occur.</span></div>
        </section>
        <aside className="payout-summary">
          <span className="eyebrow inverse">Return summary</span>
          <h2>{session.id}</h2>
          <div className="summary-counts"><span><small>Accepted items</small><strong>{session.events.filter((event) => event.result === 'accepted').length}</strong></span><span><small>Rejected items</small><strong>{session.events.filter((event) => event.result === 'rejected').length}</strong></span></div>
          <div className="summary-line"><span>Return value</span><strong>{formatMoney(total)}</strong></div>
          <div className="summary-line"><span>Fees</span><strong>RM0.00</strong></div>
          <div className="summary-total"><span>Total payout</span><strong>{formatMoney(total)}</strong></div>
          {selected && <div className="summary-destination"><CreditCard /><span><small>Sending to</small><strong>{selected.maskedIdentifier}</strong></span></div>}
        </aside>
      </div>
    </div>
  )
}

function Receipt({ sessionId, total, itemCount, method, transactionId, paidAt }: { sessionId: string; total: number; itemCount: number; method: string; transactionId: string; paidAt: string }) {
  return (
    <article className="receipt-panel">
      <div className="receipt-success"><span><Check /></span><small>Payment complete</small><strong>{formatMoney(total)}</strong><h2>Thank you for helping keep your community clean.</h2><p>{itemCount} {itemCount === 1 ? 'container has' : 'containers have'} been recorded for recycling.</p><small>Sent to {method}</small></div>
      <div className="receipt-details">
        <span><small>Return session</small><strong className="mono">{sessionId}</strong></span>
        <span><small>Transaction reference</small><strong className="mono">{transactionId}</strong></span>
        <span><small>Date and time</small><strong>{formatDateTime(paidAt)}</strong></span>
        <span><small>Transaction type</small><strong>Simulated prototype payout</strong></span>
      </div>
      <footer><ReceiptText /><span>This receipt confirms a demonstration transaction only. No funds were transferred.</span></footer>
    </article>
  )
}
