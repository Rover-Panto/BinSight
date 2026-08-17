import {
  ArrowRight,
  Bot,
  Building2,
  ChevronDown,
  Clock3,
  ExternalLink,
  LifeBuoy,
  Mail,
  MessageCircleMore,
  Phone,
  Search,
  Send,
  ShieldAlert,
  UserRound,
} from 'lucide-react'
import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { AssistantNotice } from '../components/AppShell'
import { EmptyState, InlineNotice, PageHeading, StatusBadge } from '../components/UI'
import { faqItems } from '../model'
import { useStore } from '../store'

export function FAQPage() {
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('All')
  const categories = ['All', ...Array.from(new Set(faqItems.map((item) => item.category)))]
  const results = faqItems.filter((item) => (category === 'All' || item.category === category) && `${item.question} ${item.answer}`.toLowerCase().includes(query.toLowerCase()))
  return (
    <div className="page-stack narrow-page">
      <PageHeading title="Frequently asked questions" description="Answers about returns, payouts, collection services and account privacy." />
      <div className="faq-search"><Search /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search questions" aria-label="Search frequently asked questions" /></div>
      <div className="faq-categories" role="tablist" aria-label="FAQ category">{categories.map((entry) => <button key={entry} type="button" className={category === entry ? 'active' : ''} onClick={() => setCategory(entry)}>{entry}</button>)}</div>
      {results.length ? <div className="faq-list">{results.map((item) => <details key={item.question}><summary><span><small>{item.category}</small><strong>{item.question}</strong></span><ChevronDown /></summary><p>{item.answer}</p></details>)}</div> : <EmptyState icon={<Search />} title="No matching answer" detail="Try another phrase or ask the BinSight Assistant." action={<Link className="button secondary" to="/chat">Open chat</Link>} />}
      <section className="support-cta"><LifeBuoy /><div><span className="eyebrow inverse">Still need help?</span><h2>Contact demonstration support</h2><p>Use scripted chat or view the fictional contact channels.</p></div><Link className="button light" to="/contact">Contact details <ArrowRight /></Link></section>
    </div>
  )
}

interface ChatMessage {
  id: string
  role: 'assistant' | 'user'
  text: string
  createdAt: string
}

const suggestions = [
  'Which containers can I return?',
  'When is my next collection?',
  'Where do batteries go?',
  'What is the status of WR-2461?',
]

function getScriptedReply(input: string) {
  const text = input.toLowerCase()
  if (text.includes('container') || text.includes('return') || text.includes('bottle') || text.includes('can')) return 'The prototype accepts eligible aluminium cans and plastic drink bottles. Containers should be empty, uncrushed and have a readable barcode and deposit mark. Each accepted item adds RM0.20.'
  if (text.includes('collection') || text.includes('pickup day')) return 'The next demonstration collection is garbage on Wednesday, followed by recycling on Thursday and organic waste on Saturday. Open Collection Schedule for preparation times.'
  if (text.includes('battery') || text.includes('electronic') || text.includes('e-waste')) return 'Batteries should go to a battery or e-waste drop-off point, not a household bin. Tape exposed terminals and use Locations to find the nearest demonstration facility.'
  if (text.includes('wr-2461') || text.includes('report status')) return 'Report WR-2461 is Assigned. A mock collection crew has been notified. You can view its full status timeline under My Reports.'
  if (text.includes('payout') || text.includes('money') || text.includes('bank') || text.includes('wallet')) return 'Simulated payouts can be sent to a saved Bank Transfer or E-Wallet method. Open Activity History for completed return receipts.'
  if (text.includes('human') || text.includes('contact') || text.includes('support')) return 'I am an automated demonstration assistant. For further help, open Contact to view the fictional hotline, email and service hours.'
  if (text.includes('hazard') || text.includes('sharp') || text.includes('chemical')) return 'Do not touch hazardous material or discarded sharps. Move away from immediate danger and contact emergency services when necessary. You can submit a non-urgent waste report when it is safe.'
  return 'I can help with return eligibility, RM0.20 payouts, collection dates, sorting guidance and report tracking. Try asking what to do with a specific item, or open Contact for additional demonstration support.'
}

export function ChatPage() {
  const { data } = useStore()
  const [messages, setMessages] = useState<ChatMessage[]>([
    { id: 'welcome', role: 'assistant', text: 'Hello. I am the BinSight Assistant. I can help with returns, disposal guidance, collection dates and report tracking.', createdAt: new Date().toISOString() },
  ])
  const [input, setInput] = useState('')
  const [typing, setTyping] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const sendMessage = (text: string) => {
    const trimmed = text.trim()
    if (!trimmed || typing) return
    setMessages((current) => [...current, { id: crypto.randomUUID(), role: 'user', text: trimmed, createdAt: new Date().toISOString() }])
    setInput('')
    setTyping(true)
    window.setTimeout(() => {
      setMessages((current) => [...current, { id: crypto.randomUUID(), role: 'assistant', text: getScriptedReply(trimmed), createdAt: new Date().toISOString() }])
      setTyping(false)
    }, 700)
  }

  const submit = (event: React.FormEvent) => { event.preventDefault(); sendMessage(input) }
  const activeReport = data.reports.find((report) => report.status !== 'Resolved')

  return (
    <div className="chat-page">
      <PageHeading title="BinSight Assistant" description="Scripted support for common waste-service questions." actions={<StatusBadge tone="success"><span className="live-dot" /> Automated service online</StatusBadge>} />
      <div className="chat-layout">
        <section className="chat-window">
          <AssistantNotice />
          <div className="chat-messages" aria-live="polite" aria-label="Chat conversation">
            {messages.map((message) => <article key={message.id} className={`chat-message ${message.role}`}><span>{message.role === 'assistant' ? <Bot /> : <UserRound />}</span><div><small>{message.role === 'assistant' ? 'BinSight Assistant' : 'You'} · {new Date(message.createdAt).toLocaleTimeString('en-MY', { hour: '2-digit', minute: '2-digit' })}</small><p>{message.text}</p></div></article>)}
            {typing && <article className="chat-message assistant typing" role="status"><span><Bot /></span><div><small>BinSight Assistant</small><p><i /><i /><i /><span className="sr-only">Assistant is typing</span></p></div></article>}
          </div>
          <div className="chat-suggestions"><span>Suggested questions</span><div>{suggestions.map((suggestion) => <button type="button" key={suggestion} onClick={() => sendMessage(suggestion)}>{suggestion}</button>)}</div></div>
          <form className="chat-composer" onSubmit={submit}><input ref={inputRef} value={input} onChange={(event) => setInput(event.target.value)} placeholder="Ask about waste services" aria-label="Chat message" /><button className="button primary" type="submit" disabled={!input.trim() || typing}><Send /> <span>Send</span></button></form>
        </section>
        <aside className="chat-context">
          <span className="eyebrow">Useful context</span>
          <div><strong>Next collection</strong><span>Garbage · Wednesday</span></div>
          <div><strong>Open report</strong><span>{activeReport ? `${activeReport.id} · ${activeReport.status}` : 'No open reports'}</span></div>
          <div><strong>Return rate</strong><span>RM0.20 per accepted item</span></div>
          <Link to="/faq"><MessageCircleMore /> Browse FAQ <ArrowRight /></Link>
          <Link to="/contact"><Phone /> Contact details <ArrowRight /></Link>
        </aside>
      </div>
    </div>
  )
}

export function ContactPage() {
  const contacts = [
    { icon: Phone, label: 'Demonstration hotline', value: '+60 3-0000 0000', detail: 'Monday to Friday, 8:00 AM–6:00 PM', href: 'tel:+60300000000' },
    { icon: Mail, label: 'Prototype support email', value: 'help@binsight.example', detail: 'Mock responses within one working day', href: 'mailto:help@binsight.example' },
    { icon: Building2, label: 'Demonstration centre', value: 'BinSight Demonstration Centre', detail: 'Kuala Lumpur, Malaysia', href: undefined },
  ]
  return (
    <div className="page-stack narrow-page">
      <PageHeading title="Contact BinSight" description="Fictional channels for testing the resident-support experience." actions={<StatusBadge tone="neutral">Demonstration details</StatusBadge>} />
      <InlineNotice tone="warning" title="These contacts are not operational">Phone numbers, email addresses, locations and service times on this page are fictional.</InlineNotice>
      <div className="contact-list">{contacts.map(({ icon: Icon, label, value, detail, href }) => { const content = <><span className="contact-icon"><Icon /></span><span><small>{label}</small><strong>{value}</strong><p>{detail}</p></span>{href && <ExternalLink />}</>; return href ? <a key={label} href={href}>{content}</a> : <div key={label}>{content}</div> })}</div>
      <section className="hours-panel"><div><Clock3 /><span><strong>Mock support hours</strong><small>Malaysia time</small></span></div><dl><div><dt>Monday–Friday</dt><dd>8:00 AM–6:00 PM</dd></div><div><dt>Saturday</dt><dd>9:00 AM–1:00 PM</dd></div><div><dt>Sunday and public holidays</dt><dd>Closed</dd></div></dl></section>
      <section className="emergency-panel"><ShieldAlert /><div><h2>Immediate danger or emergency</h2><p>Do not rely on an app report for fire, chemical exposure, dangerous obstructions or medical emergencies. Move to safety and contact the appropriate Malaysian emergency service.</p></div></section>
      <section className="support-options"><Link to="/chat"><Bot /><span><strong>Ask the automated assistant</strong><small>Scripted guidance is available at any time.</small></span><ArrowRight /></Link><Link to="/faq"><LifeBuoy /><span><strong>Browse common questions</strong><small>Returns, payouts, collections and privacy.</small></span><ArrowRight /></Link></section>
    </div>
  )
}
