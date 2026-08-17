import { useEffect, useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { WifiOff } from 'lucide-react'
import { AppShell } from './components/AppShell'
import { LoginPage, VerifyPage } from './pages/AuthPages'
import { AccountPage, HistoryPage, HomePage, NotificationsPage, PayoutMethodsPage } from './pages/HomeAccountPages'
import { PayoutPage, ReturnLandingPage, ReturnSessionPage } from './pages/ReturnPages'
import { BulkyPickupPage, LocationsPage, ReportDetailPage, ReportIssuePage, ReportsPage, SchedulePage, ServicesPage, SortingGuidePage } from './pages/ServicePages'
import { ChatPage, ContactPage, FAQPage } from './pages/SupportPages'
import { useStore } from './store'

function ProtectedLayout() {
  const { data } = useStore()
  if (!data.auth.authenticated) return <Navigate to="/login" replace />
  return <AppShell />
}

function OfflineBanner() {
  const [online, setOnline] = useState(navigator.onLine)
  useEffect(() => {
    const update = () => setOnline(navigator.onLine)
    window.addEventListener('online', update)
    window.addEventListener('offline', update)
    return () => {
      window.removeEventListener('online', update)
      window.removeEventListener('offline', update)
    }
  }, [])
  if (online) return null
  return <div className="offline-banner" role="status"><WifiOff /> Offline mode · saved demonstration data remains available</div>
}

function NotFoundPage() {
  return <div className="not-found"><span>404 / ROUTE</span><h1>This service page is unavailable.</h1><p>The address may have changed or the demonstration route does not exist.</p><a className="button primary" href="/">Return home</a></div>
}

export default function App() {
  return (
    <>
      <OfflineBanner />
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/verify" element={<VerifyPage />} />
        <Route element={<ProtectedLayout />}>
          <Route index element={<HomePage />} />
          <Route path="return" element={<ReturnLandingPage />} />
          <Route path="return/:id" element={<ReturnSessionPage />} />
          <Route path="payout/:id" element={<PayoutPage />} />
          <Route path="report" element={<ReportIssuePage />} />
          <Route path="reports" element={<ReportsPage />} />
          <Route path="reports/:id" element={<ReportDetailPage />} />
          <Route path="services" element={<ServicesPage />} />
          <Route path="schedule" element={<SchedulePage />} />
          <Route path="guide" element={<SortingGuidePage />} />
          <Route path="locations" element={<LocationsPage />} />
          <Route path="bulky-pickup" element={<BulkyPickupPage />} />
          <Route path="faq" element={<FAQPage />} />
          <Route path="chat" element={<ChatPage />} />
          <Route path="contact" element={<ContactPage />} />
          <Route path="notifications" element={<NotificationsPage />} />
          <Route path="history" element={<HistoryPage />} />
          <Route path="account" element={<AccountPage />} />
          <Route path="payout-methods" element={<PayoutMethodsPage />} />
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </>
  )
}
