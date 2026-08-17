import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import {
  createDefaultData,
  createReference,
  reportStatuses,
  type AppData,
  type AppSettings,
  type ItemType,
  type MethodType,
  type PayoutMethod,
  type WasteReport,
} from './model'

const STORAGE_KEY = 'binsight-demo-v1'

const loadData = (): AppData => {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (!stored) return createDefaultData()
    const parsed = JSON.parse(stored) as AppData
    return parsed.version === 1 ? parsed : createDefaultData()
  } catch {
    return createDefaultData()
  }
}

interface NewReport {
  category: string
  location: string
  description: string
  observedAt: string
  hazardous: boolean
  imageNames: string[]
}

interface StoreValue {
  data: AppData
  login: () => void
  logout: () => void
  createReturn: () => string
  addItem: (sessionId: string, type: ItemType) => void
  retryItem: (sessionId: string, type: ItemType) => void
  finishReturn: (sessionId: string) => void
  payReturn: (sessionId: string, methodId: string) => { ok: boolean; transactionId?: string }
  addPayoutMethod: (type: MethodType, lastFour: string) => void
  removePayoutMethod: (id: string) => void
  setDefaultMethod: (id: string) => void
  createReport: (report: NewReport) => string
  advanceReport: (id: string) => void
  reopenReport: (id: string) => void
  rateReport: (id: string, rating: number) => void
  markNotificationRead: (id: string) => void
  markAllNotificationsRead: () => void
  updateSettings: (settings: Partial<AppSettings>) => void
  resetDemo: () => void
}

const StoreContext = createContext<StoreValue | null>(null)

export function StoreProvider({ children }: { children: ReactNode }) {
  const [data, setData] = useState<AppData>(loadData)

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data))
  }, [data])

  const value = useMemo<StoreValue>(() => ({
    data,
    login: () =>
      setData((current) => ({
        ...current,
        auth: {
          authenticated: true,
          userId: current.auth.userId ?? `demo-${crypto.randomUUID().slice(0, 8)}`,
        },
      })),
    logout: () =>
      setData((current) => ({
        ...current,
        auth: { authenticated: false, userId: current.auth.userId },
      })),
    createReturn: () => {
      const id = createReference('BS')
      setData((current) => ({
        ...current,
        returns: [
          {
            id,
            status: 'active',
            events: [],
            createdAt: new Date().toISOString(),
          },
          ...current.returns,
        ],
      }))
      return id
    },
    addItem: (sessionId, type) =>
      setData((current) => {
        const result = current.settings.nextItemOutcome
        const event = {
          id: crypto.randomUUID(),
          type,
          result,
          reason: result === 'rejected' ? current.settings.rejectedReason : undefined,
          valueCents: result === 'accepted' ? 20 : 0,
          createdAt: new Date().toISOString(),
        } as const
        return {
          ...current,
          returns: current.returns.map((session) =>
            session.id === sessionId
              ? { ...session, events: [...session.events, event] }
              : session,
          ),
        }
      }),
    retryItem: (sessionId, type) =>
      setData((current) => {
        const event = {
          id: crypto.randomUUID(),
          type,
          result: 'accepted' as const,
          valueCents: 20,
          createdAt: new Date().toISOString(),
        }
        return {
          ...current,
          returns: current.returns.map((session) =>
            session.id === sessionId
              ? { ...session, events: [...session.events, event] }
              : session,
          ),
        }
      }),
    finishReturn: (sessionId) =>
      setData((current) => ({
        ...current,
        returns: current.returns.map((session) =>
          session.id === sessionId
            ? { ...session, status: 'awaiting-payout' }
            : session,
        ),
      })),
    payReturn: (sessionId, methodId) => {
      if (data.settings.failNextPayment) {
        setData((current) => ({
          ...current,
          settings: { ...current.settings, failNextPayment: false },
        }))
        return { ok: false }
      }
      const transactionId = `TXN-${sessionId.replace('-', '')}-${Math.random().toString(36).slice(2, 6).toUpperCase()}`
      const paidAt = new Date().toISOString()
      const method = data.payoutMethods.find((entry) => entry.id === methodId)
      const session = data.returns.find((entry) => entry.id === sessionId)
      const total = session?.events.reduce((sum, event) => sum + event.valueCents, 0) ?? 0
      setData((current) => ({
        ...current,
        returns: current.returns.map((entry) =>
          entry.id === sessionId
            ? { ...entry, status: 'paid', paidAt, payoutMethodId: methodId, transactionId }
            : entry,
        ),
        notifications: [
          {
            id: crypto.randomUUID(),
            title: `${(total / 100).toLocaleString('en-MY', { style: 'currency', currency: 'MYR' })} sent`,
            detail: `Return ${sessionId} was paid to ${method?.maskedIdentifier ?? 'the selected method'}.`,
            createdAt: paidAt,
            read: false,
            kind: 'payout',
          },
          ...current.notifications,
        ],
      }))
      return { ok: true, transactionId }
    },
    addPayoutMethod: (type, lastFour) =>
      setData((current) => {
        const method: PayoutMethod = {
          id: crypto.randomUUID(),
          type,
          label: type === 'bank' ? 'Bank Transfer' : 'E-Wallet',
          maskedIdentifier: `${type === 'bank' ? 'Bank account' : 'E-Wallet'} •••• ${lastFour}`,
          isDefault: current.payoutMethods.length === 0,
        }
        return { ...current, payoutMethods: [...current.payoutMethods, method] }
      }),
    removePayoutMethod: (id) =>
      setData((current) => {
        const removed = current.payoutMethods.find((method) => method.id === id)
        const remaining = current.payoutMethods.filter((method) => method.id !== id)
        if (removed?.isDefault && remaining[0]) remaining[0] = { ...remaining[0], isDefault: true }
        return { ...current, payoutMethods: remaining }
      }),
    setDefaultMethod: (id) =>
      setData((current) => ({
        ...current,
        payoutMethods: current.payoutMethods.map((method) => ({
          ...method,
          isDefault: method.id === id,
        })),
      })),
    createReport: (report) => {
      const id = createReference('WR')
      const createdAt = new Date().toISOString()
      const entry: WasteReport = { ...report, id, status: 'Submitted', createdAt }
      setData((current) => ({
        ...current,
        reports: [entry, ...current.reports],
        notifications: [
          {
            id: crypto.randomUUID(),
            title: 'Report submitted',
            detail: `${id} has been recorded for review.`,
            createdAt,
            read: false,
            kind: 'report',
          },
          ...current.notifications,
        ],
      }))
      return id
    },
    advanceReport: (id) =>
      setData((current) => ({
        ...current,
        reports: current.reports.map((report) => {
          if (report.id !== id) return report
          const index = reportStatuses.indexOf(report.status)
          return { ...report, status: reportStatuses[Math.min(index + 1, reportStatuses.length - 1)] }
        }),
      })),
    reopenReport: (id) =>
      setData((current) => ({
        ...current,
        reports: current.reports.map((report) =>
          report.id === id ? { ...report, status: 'Reviewed', rating: undefined } : report,
        ),
      })),
    rateReport: (id, rating) =>
      setData((current) => ({
        ...current,
        reports: current.reports.map((report) =>
          report.id === id ? { ...report, rating } : report,
        ),
      })),
    markNotificationRead: (id) =>
      setData((current) => ({
        ...current,
        notifications: current.notifications.map((notification) =>
          notification.id === id ? { ...notification, read: true } : notification,
        ),
      })),
    markAllNotificationsRead: () =>
      setData((current) => ({
        ...current,
        notifications: current.notifications.map((notification) => ({ ...notification, read: true })),
      })),
    updateSettings: (settings) =>
      setData((current) => ({
        ...current,
        settings: { ...current.settings, ...settings },
      })),
    resetDemo: () =>
      setData((current) => ({
        ...createDefaultData(),
        auth: current.auth,
      })),
  }), [data])

  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>
}

// oxlint-disable-next-line react/only-export-components
export function useStore() {
  const store = useContext(StoreContext)
  if (!store) throw new Error('useStore must be used inside StoreProvider')
  return store
}
