import { ArrowLeft, ArrowRight, CheckCircle2, KeyRound, LockKeyhole, Recycle, ShieldCheck } from 'lucide-react'
import { useEffect, useRef, useState, type ClipboardEvent, type KeyboardEvent } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { Field, InlineNotice } from '../components/UI'
import { useStore } from '../store'

function AuthVisual() {
  return (
    <section className="auth-visual" aria-label="BinSight prototype information">
      <div className="auth-brand">
        <span className="auth-mark"><Recycle aria-hidden="true" /></span>
        <div><strong>BinSight</strong><small>Citizen waste hub</small></div>
      </div>
      <div className="industrial-scene" aria-hidden="true">
        <div className="scene-grid" />
        <div className="scene-bin bin-one"><span>01</span><i /></div>
        <div className="scene-bin bin-two"><span>02</span><i /></div>
        <div className="scene-station"><span>RETURN</span><strong>RM0.20</strong><small>per accepted item</small></div>
        <div className="scene-rail"><i /><i /><i /></div>
      </div>
      <div className="auth-statement">
        <span>DEMONSTRATION SYSTEM / MALAYSIA</span>
        <h1>One place for returns, recycling and local waste services.</h1>
        <p>Prototype services and payouts are simulated. No government affiliation is implied.</p>
      </div>
    </section>
  )
}

export function LoginPage() {
  const { data } = useStore()
  const navigate = useNavigate()
  const [nid, setNid] = useState('')
  const [error, setError] = useState('')

  if (data.auth.authenticated) return <Navigate to="/" replace />

  const submit = (event: React.FormEvent) => {
    event.preventDefault()
    const cleaned = nid.replace(/\s/g, '')
    if (cleaned.length < 6) {
      setError('Enter at least 6 characters for the demonstration ID.')
      return
    }
    navigate('/verify', { state: { mask: `•••• ${cleaned.slice(-4)}` } })
  }

  return (
    <main className="auth-layout">
      <AuthVisual />
      <section className="auth-form-wrap">
        <div className="auth-form-panel">
          <span className="eyebrow">Secure prototype access</span>
          <h2>Sign in with National ID</h2>
          <p className="lead">Use demonstration information only. Your entered ID will not be stored.</p>
          <form onSubmit={submit} noValidate>
            <Field label="National ID" hint="Any fictional ID with at least 6 characters." error={error}>
              <div className="input-with-icon">
                <ShieldCheck aria-hidden="true" />
                <input
                  aria-label="National ID"
                  autoComplete="off"
                  autoFocus
                  value={nid}
                  onChange={(event) => { setNid(event.target.value); setError('') }}
                  placeholder="Enter demonstration ID"
                  aria-invalid={Boolean(error)}
                />
              </div>
            </Field>
            <button className="button primary wide" type="submit">Send mock OTP <ArrowRight aria-hidden="true" /></button>
          </form>
          <div className="auth-security"><LockKeyhole aria-hidden="true" /><span>Only a generated user reference and login state persist on this device.</span></div>
        </div>
        <footer className="auth-footer"><strong>Prototype by MON BLUE</strong><span>BinSight / DEMO 01</span></footer>
      </section>
    </main>
  )
}

export function VerifyPage() {
  const { data, login } = useStore()
  const navigate = useNavigate()
  const location = useLocation()
  const state = location.state as { mask?: string } | null
  const [digits, setDigits] = useState(['', '', '', '', '', ''])
  const [error, setError] = useState('')
  const [seconds, setSeconds] = useState(45)
  const [resent, setResent] = useState(false)
  const refs = useRef<Array<HTMLInputElement | null>>([])

  useEffect(() => {
    const timer = window.setInterval(() => setSeconds((current) => Math.max(0, current - 1)), 1000)
    return () => window.clearInterval(timer)
  }, [])

  if (data.auth.authenticated) return <Navigate to="/" replace />
  if (!state?.mask) return <Navigate to="/login" replace />

  const updateDigit = (index: number, value: string) => {
    const digit = value.replace(/\D/g, '').slice(-1)
    setDigits((current) => current.map((item, itemIndex) => itemIndex === index ? digit : item))
    setError('')
    if (digit && index < 5) refs.current[index + 1]?.focus()
  }

  const keyDown = (index: number, event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Backspace' && !digits[index] && index > 0) refs.current[index - 1]?.focus()
  }

  const paste = (event: ClipboardEvent<HTMLDivElement>) => {
    const code = event.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6)
    if (code.length === 6) {
      event.preventDefault()
      setDigits(code.split(''))
      refs.current[5]?.focus()
    }
  }

  const verify = (event: React.FormEvent) => {
    event.preventDefault()
    if (seconds === 0) {
      setError('This demonstration code has expired. Request a new code.')
      return
    }
    if (digits.join('') !== '123456') {
      setError('That code is not valid. Use 123456 for this prototype.')
      return
    }
    login()
    navigate('/', { replace: true })
  }

  const resend = () => {
    setSeconds(45)
    setDigits(['', '', '', '', '', ''])
    setError('')
    setResent(true)
    refs.current[0]?.focus()
  }

  return (
    <main className="auth-layout">
      <AuthVisual />
      <section className="auth-form-wrap">
        <div className="auth-form-panel">
          <Link className="text-link back-link" to="/login"><ArrowLeft aria-hidden="true" /> Edit National ID</Link>
          <span className="eyebrow">Identity verification</span>
          <h2>Enter the 6-digit code</h2>
          <p className="lead">A mock code was sent to the registered mobile for ID {state.mask}.</p>
          {resent && <InlineNotice tone="success" title="New code issued">Use the demonstration code shown below.</InlineNotice>}
          <form onSubmit={verify} noValidate>
            <div className="demo-code"><KeyRound aria-hidden="true" /><span>Demo code</span><strong>123456</strong></div>
            <div className="otp-group" onPaste={paste} aria-label="One-time password">
              {digits.map((digit, index) => (
                <input
                  key={index}
                  ref={(element) => { refs.current[index] = element }}
                  value={digit}
                  onChange={(event) => updateDigit(index, event.target.value)}
                  onKeyDown={(event) => keyDown(index, event)}
                  inputMode="numeric"
                  autoComplete={index === 0 ? 'one-time-code' : 'off'}
                  aria-label={`OTP digit ${index + 1}`}
                  maxLength={1}
                />
              ))}
            </div>
            {error && <p className="form-error" role="alert">{error}</p>}
            <div className="otp-meta">
              <span>{seconds > 0 ? `Code expires in 00:${seconds.toString().padStart(2, '0')}` : 'Code expired'}</span>
              <button className="text-button" type="button" onClick={resend} disabled={seconds > 30}>Resend code</button>
            </div>
            <button className="button primary wide" type="submit">Verify and continue <CheckCircle2 aria-hidden="true" /></button>
          </form>
        </div>
        <footer className="auth-footer"><strong>Prototype by MON BLUE</strong><span>BinSight / DEMO 01</span></footer>
      </section>
    </main>
  )
}
