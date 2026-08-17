export type ItemType = 'Can' | 'Bottle'
export type ItemResult = 'accepted' | 'rejected'
export type ReturnStatus = 'active' | 'awaiting-payout' | 'paid'
export type MethodType = 'bank' | 'wallet'
export type ReportStatus = 'Submitted' | 'Reviewed' | 'Assigned' | 'Resolved'

export interface ItemEvent {
  id: string
  type: ItemType
  result: ItemResult
  reason?: string
  valueCents: number
  createdAt: string
}

export interface ReturnSession {
  id: string
  status: ReturnStatus
  events: ItemEvent[]
  createdAt: string
  paidAt?: string
  payoutMethodId?: string
  transactionId?: string
}

export interface PayoutMethod {
  id: string
  type: MethodType
  label: string
  maskedIdentifier: string
  isDefault: boolean
}

export interface WasteReport {
  id: string
  category: string
  location: string
  description: string
  observedAt: string
  hazardous: boolean
  imageNames: string[]
  status: ReportStatus
  createdAt: string
  rating?: number
}

export interface AppNotification {
  id: string
  title: string
  detail: string
  createdAt: string
  read: boolean
  kind: 'service' | 'report' | 'payout'
}

export interface AppSettings {
  reminders: boolean
  serviceAlerts: boolean
  nextItemOutcome: ItemResult
  rejectedReason: string
  failNextPayment: boolean
}

export interface AppData {
  version: 1
  auth: {
    authenticated: boolean
    userId: string | null
  }
  returns: ReturnSession[]
  payoutMethods: PayoutMethod[]
  reports: WasteReport[]
  notifications: AppNotification[]
  settings: AppSettings
}

export const reportStatuses: ReportStatus[] = [
  'Submitted',
  'Reviewed',
  'Assigned',
  'Resolved',
]

export const rejectedReasons = [
  'Barcode could not be read',
  'Deposit mark not found',
  'Container is crushed',
  'Unsupported item',
]

export const reportCategories = [
  'Overflowing public bin',
  'Illegal dumping or litter',
  'Missed collection',
  'Damaged, missing or inaccessible bin',
  'Contaminated recycling',
  'Hazardous waste',
  'Discarded sharps',
  'Return station fault',
  'Other waste issue',
]

const now = new Date()
const hoursAgo = (hours: number) =>
  new Date(now.getTime() - hours * 60 * 60 * 1000).toISOString()

export const createDefaultData = (): AppData => ({
  version: 1,
  auth: { authenticated: false, userId: null },
  returns: [
    {
      id: 'BS-1036',
      status: 'paid',
      createdAt: hoursAgo(52),
      paidAt: hoursAgo(51.8),
      payoutMethodId: 'method-bank',
      transactionId: 'TXN-BS1036-A7K2',
      events: [
        {
          id: 'evt-1',
          type: 'Can',
          result: 'accepted',
          valueCents: 20,
          createdAt: hoursAgo(51.95),
        },
        {
          id: 'evt-2',
          type: 'Bottle',
          result: 'accepted',
          valueCents: 20,
          createdAt: hoursAgo(51.9),
        },
        {
          id: 'evt-3',
          type: 'Bottle',
          result: 'accepted',
          valueCents: 20,
          createdAt: hoursAgo(51.85),
        },
      ],
    },
  ],
  payoutMethods: [
    {
      id: 'method-bank',
      type: 'bank',
      label: 'Bank Transfer',
      maskedIdentifier: 'Bank account •••• 4821',
      isDefault: true,
    },
    {
      id: 'method-wallet',
      type: 'wallet',
      label: 'E-Wallet',
      maskedIdentifier: 'E-Wallet •••• 7712',
      isDefault: false,
    },
  ],
  reports: [
    {
      id: 'WR-2461',
      category: 'Overflowing public bin',
      location: 'Jalan Universiti, Petaling Jaya',
      description:
        'Public bin beside the pedestrian crossing is full and loose packaging is reaching the walkway.',
      observedAt: hoursAgo(28),
      hazardous: false,
      imageNames: ['overflow-location.jpg'],
      status: 'Assigned',
      createdAt: hoursAgo(27.5),
    },
    {
      id: 'WR-2398',
      category: 'Damaged, missing or inaccessible bin',
      location: 'Persiaran Barat community stop',
      description: 'Recycling-bin lid hinge was detached.',
      observedAt: hoursAgo(170),
      hazardous: false,
      imageNames: [],
      status: 'Resolved',
      createdAt: hoursAgo(169),
      rating: 4,
    },
  ],
  notifications: [
    {
      id: 'note-1',
      title: 'Report assigned',
      detail: 'WR-2461 has been assigned to a collection crew.',
      createdAt: hoursAgo(3),
      read: false,
      kind: 'report',
    },
    {
      id: 'note-2',
      title: 'Recycling collection change',
      detail: 'Thursday collection will begin two hours earlier this week.',
      createdAt: hoursAgo(20),
      read: false,
      kind: 'service',
    },
    {
      id: 'note-3',
      title: 'RM0.60 sent',
      detail: 'Return BS-1036 was paid to Bank account •••• 4821.',
      createdAt: hoursAgo(51.8),
      read: true,
      kind: 'payout',
    },
  ],
  settings: {
    reminders: true,
    serviceAlerts: true,
    nextItemOutcome: 'accepted',
    rejectedReason: rejectedReasons[0],
    failNextPayment: false,
  },
})

export const disposalItems = [
  { item: 'Aluminium drink can', destination: 'Return station', preparation: 'Empty. Keep the barcode and deposit mark readable.', group: 'Packaging' },
  { item: 'Plastic drink bottle', destination: 'Return station', preparation: 'Empty. Do not crush the bottle.', group: 'Packaging' },
  { item: 'Glass bottle', destination: 'Glass recycling point', preparation: 'Rinse and remove the cap.', group: 'Glass' },
  { item: 'Cardboard box', destination: 'Recycling bin', preparation: 'Flatten and keep dry.', group: 'Paper' },
  { item: 'Food scraps', destination: 'Organic waste', preparation: 'Remove packaging and liquids.', group: 'Organics' },
  { item: 'Household battery', destination: 'Battery drop-off', preparation: 'Tape exposed terminals.', group: 'Hazardous' },
  { item: 'Mobile phone', destination: 'E-waste point', preparation: 'Remove personal data and accessories.', group: 'Electronics' },
  { item: 'Light bulb', destination: 'Hazardous-waste facility', preparation: 'Wrap securely. Do not place in glass recycling.', group: 'Hazardous' },
  { item: 'Clothing', destination: 'Textile donation point', preparation: 'Clean and bag dry items.', group: 'Textiles' },
  { item: 'Used cooking oil', destination: 'Oil recovery point', preparation: 'Cool and seal in a labelled container.', group: 'Hazardous' },
  { item: 'Sofa', destination: 'Bulky-item pickup', preparation: 'Book a collection before placing outside.', group: 'Bulky items' },
  { item: 'Disposable diaper', destination: 'General waste', preparation: 'Seal securely in a bag.', group: 'General waste' },
]

export const serviceLocations = [
  { id: 'loc-1', name: 'BinSight Central Return Point', type: 'Return station', distance: 0.8, hours: '07:00–22:00', materials: 'Cans and plastic bottles', x: 35, y: 32 },
  { id: 'loc-2', name: 'Community Recycling Hub', type: 'Recycling centre', distance: 1.6, hours: '08:00–18:00', materials: 'Paper, glass, metal and plastics', x: 67, y: 44 },
  { id: 'loc-3', name: 'PJ E-Waste Collection Point', type: 'E-waste point', distance: 2.4, hours: '09:00–17:00', materials: 'Small electronics and batteries', x: 48, y: 68 },
  { id: 'loc-4', name: 'District Recovery Facility', type: 'Hazardous waste', distance: 4.9, hours: '08:30–16:30', materials: 'Bulbs, oil and household chemicals', x: 77, y: 75 },
]

export const faqItems = [
  { category: 'Returns', question: 'Which containers can I return?', answer: 'The prototype accepts eligible aluminium cans and plastic drink bottles with a readable barcode and deposit mark.' },
  { category: 'Returns', question: 'Why was my item rejected?', answer: 'Common reasons include an unreadable barcode, missing deposit mark, a crushed container or an unsupported material.' },
  { category: 'Payouts', question: 'How much is each accepted item worth?', answer: 'Each accepted item adds 20 sen, displayed as RM0.20, to the session payout.' },
  { category: 'Payouts', question: 'Where can the payout be sent?', answer: 'Choose a saved Bank Transfer or E-Wallet method. All prototype payouts are simulated.' },
  { category: 'Collections', question: 'How do reminders work?', answer: 'Enable reminders in Account to receive a mock alert before garbage, recycling and organic collection.' },
  { category: 'Reporting', question: 'What information makes a useful report?', answer: 'Include a precise location, a clear description, the time observed and photos when it is safe to take them.' },
  { category: 'Recycling', question: 'Where do batteries go?', answer: 'Take household batteries to a battery or e-waste drop-off point. Tape exposed terminals first.' },
  { category: 'Account', question: 'Can I remove a payout method?', answer: 'Yes. Open Payout Methods in Account and confirm removal. Add a method before requesting another payout.' },
  { category: 'Privacy', question: 'Does the prototype store my National ID?', answer: 'No. The entered National ID and OTP are not stored. Only a generated demonstration user ID and login state persist.' },
]

export const formatMoney = (cents: number) => `RM${(cents / 100).toFixed(2)}`

export const formatDateTime = (iso: string) =>
  new Intl.DateTimeFormat('en-MY', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(iso))

export const getSessionTotal = (session: ReturnSession) =>
  session.events.reduce((total, event) => total + event.valueCents, 0)

export const createReference = (prefix: string) =>
  `${prefix}-${Math.floor(1000 + Math.random() * 9000)}`

