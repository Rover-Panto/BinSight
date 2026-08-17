import {
  Bell,
  BookOpen,
  Bot,
  CircleUserRound,
  ClipboardList,
  Home,
  LifeBuoy,
  MapPinned,
  MessageSquareText,
  PackagePlus,
  Recycle,
  SearchCheck,
  TriangleAlert,
} from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'
import { useStore } from '../store'

const primaryNav = [
  { to: '/', label: 'Home', icon: Home },
  { to: '/return', label: 'Return', icon: Recycle },
  { to: '/report', label: 'Report', icon: TriangleAlert },
  { to: '/reports', label: 'My reports', icon: ClipboardList },
  { to: '/guide', label: 'Dispose', icon: SearchCheck },
  { to: '/services', label: 'Services', icon: MapPinned },
  { to: '/account', label: 'Account', icon: CircleUserRound },
]

const mobileNav = [
  { to: '/', label: 'Home', icon: Home },
  { to: '/return', label: 'Return', icon: Recycle },
  { to: '/report', label: 'Report', icon: TriangleAlert },
  { to: '/guide', label: 'Dispose', icon: BookOpen },
  { to: '/account', label: 'Account', icon: CircleUserRound },
]

function Brand() {
  return (
    <NavLink className="brand" to="/" aria-label="BinSight home">
      <span className="brand-mark" aria-hidden="true">
        <span />
        <span />
        <span />
      </span>
      <span>
        <strong>BinSight</strong>
        <small>Citizen waste hub</small>
      </span>
    </NavLink>
  )
}

export function AppShell() {
  const { data } = useStore()
  const unread = data.notifications.filter((item) => !item.read).length

  return (
    <div className="app-frame">
      <a className="skip-link" href="#main-content">Skip to content</a>
      <aside className="side-rail">
        <Brand />
        <nav className="side-nav" aria-label="Primary navigation">
          {primaryNav.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} end={to === '/'}>
              <Icon aria-hidden="true" />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="rail-support">
          <NavLink to="/faq"><LifeBuoy aria-hidden="true" /> Help and FAQ</NavLink>
          <NavLink to="/contact"><PackagePlus aria-hidden="true" /> Contact</NavLink>
        </div>
        <div className="prototype-stamp">
          <span>DEMO / 01</span>
          <strong>Prototype by MON BLUE</strong>
          <small>Simulated services and payouts</small>
        </div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div className="mobile-brand"><Brand /></div>
          <div className="topbar-spacer" />
          <div className="top-actions">
            <NavLink className="icon-button" to="/chat" aria-label="Open BinSight Assistant" title="Chat">
              <MessageSquareText aria-hidden="true" />
            </NavLink>
            <NavLink className="icon-button notification-button" to="/notifications" aria-label={`${unread} unread notifications`} title="Notifications">
              <Bell aria-hidden="true" />
              {unread > 0 && <span className="notification-dot">{unread}</span>}
            </NavLink>
            <NavLink className="profile-button compact-profile" to="/account" aria-label="Open account" title="Account"><span className="profile-monogram">MB</span></NavLink>
          </div>
        </header>
        <main id="main-content" className="main-content">
          <Outlet />
        </main>
      </section>

      <nav className="mobile-nav" aria-label="Mobile navigation">
        {mobileNav.map(({ to, label, icon: Icon }) => (
          <NavLink key={to} to={to} end={to === '/'}>
            <Icon aria-hidden="true" />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  )
}

export function AssistantNotice() {
  return (
    <div className="assistant-notice">
      <Bot aria-hidden="true" />
      <span><strong>Automated assistant</strong> Responses use scripted demonstration data.</span>
    </div>
  )
}
