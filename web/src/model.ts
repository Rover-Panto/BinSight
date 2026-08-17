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
  nearbyBinAlerts: boolean
  serviceAlerts: boolean
  nextItemType: ItemType
  nextItemOutcome: ItemResult
  rejectedReason: string
  failNextPayment: boolean
}

export interface AppData {
  version: 2
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
  version: 2,
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
      title: 'Smart-bin service update',
      detail: 'A nearby public bin was added to the next priority collection route.',
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
    nearbyBinAlerts: true,
    serviceAlerts: true,
    nextItemType: 'Can',
    nextItemOutcome: 'accepted',
    rejectedReason: rejectedReasons[0],
    failNextPayment: false,
  },
})

export interface DisposalCategory {
  id: string
  title: string
  destination: string
  guidance: string
  examples: string
  keywords: string[]
  tone: 'blue' | 'green' | 'amber' | 'red' | 'graphite'
}

export const disposalCategories: DisposalCategory[] = [
  {
    id: 'returns',
    title: 'Deposit containers',
    destination: 'Beverage return station',
    guidance: 'Empty the container and keep its barcode and deposit mark readable. Do not crush it.',
    examples: 'Aluminium drink cans and eligible plastic drink bottles',
    keywords: ['aluminium can', 'aluminum can', 'drink can', 'soda can', 'soft drink can', 'plastic drink bottle', 'water bottle', 'beverage bottle', 'deposit container'],
    tone: 'blue',
  },
  {
    id: 'recycling',
    title: 'Dry recyclables',
    destination: 'Community recycling point',
    guidance: 'Keep items empty, clean and dry. Separate materials when the facility requires it.',
    examples: 'Paper, cardboard, metal, glass and rigid plastic packaging',
    keywords: ['paper', 'newspaper', 'magazine', 'cardboard', 'box', 'glass bottle', 'glass jar', 'metal tin', 'steel can', 'plastic tub', 'plastic packaging'],
    tone: 'green',
  },
  {
    id: 'organic',
    title: 'Food and garden material',
    destination: 'Organic waste point',
    guidance: 'Remove packaging, liquids and non-compostable material before disposal.',
    examples: 'Food scraps, fruit peel, leaves and small garden cuttings',
    keywords: ['food', 'scrap', 'fruit', 'vegetable', 'peel', 'coffee ground', 'tea bag', 'leaf', 'leaves', 'garden', 'grass', 'branch'],
    tone: 'green',
  },
  {
    id: 'electronics',
    title: 'Electrical and electronic items',
    destination: 'E-waste collection point',
    guidance: 'Remove personal data where possible. Keep damaged devices dry and separate from household bins.',
    examples: 'Phones, cables, chargers, computers and small appliances',
    keywords: ['phone', 'mobile', 'laptop', 'computer', 'tablet', 'charger', 'cable', 'headphone', 'earbud', 'camera', 'electronic', 'e-waste', 'appliance', 'toaster', 'kettle'],
    tone: 'blue',
  },
  {
    id: 'hazardous',
    title: 'Hazardous household waste',
    destination: 'Special-handling facility',
    guidance: 'Do not open, mix or pour the material away. Secure it in its original container where possible.',
    examples: 'Batteries, lamps, paint, chemicals, oil, medicine and sharps',
    keywords: ['battery', 'bulb', 'lamp', 'paint', 'chemical', 'solvent', 'pesticide', 'oil', 'medicine', 'medication', 'needle', 'sharp', 'aerosol'],
    tone: 'red',
  },
  {
    id: 'bulky',
    title: 'Large household items',
    destination: 'Bulky-item pickup',
    guidance: 'Book a pickup before moving the item outside. Keep walkways and emergency access clear.',
    examples: 'Furniture, mattresses and large appliances',
    keywords: ['sofa', 'couch', 'chair', 'table', 'desk', 'wardrobe', 'cabinet', 'mattress', 'bed', 'fridge', 'refrigerator', 'washing machine', 'large appliance', 'furniture'],
    tone: 'amber',
  },
  {
    id: 'general',
    title: 'General waste',
    destination: 'General waste bin',
    guidance: 'Bag loose or unhygienic material securely. Do not include batteries, chemicals or recyclable containers.',
    examples: 'Diapers, contaminated packaging, ceramics and sweepings',
    keywords: ['diaper', 'nappy', 'ceramic', 'broken plate', 'broken cup', 'contaminated packaging', 'vacuum dust', 'sweeping', 'tissue', 'sanitary'],
    tone: 'graphite',
  },
]

export const classifyDisposal = (query: string) => {
  const normalized = query.trim().toLowerCase()
  if (normalized.length < 2) return null
  return disposalCategories.find((category) =>
    category.keywords.some((keyword) => normalized.includes(keyword)),
  ) ?? null
}

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
  { category: 'Collections', question: 'When are public bins collected?', answer: 'BinSight does not publish a fixed collection timetable. Sensor readings and route priority determine when a public bin is added to a collection route.' },
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
