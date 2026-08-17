import { describe, expect, it } from 'vitest'
import { classifyDisposal, formatMoney, getSessionTotal, type ReturnSession } from './model'

describe('return value calculation', () => {
  it('adds RM0.20 for accepted items and nothing for rejected items', () => {
    const session: ReturnSession = {
      id: 'BS-TEST',
      status: 'active',
      createdAt: new Date().toISOString(),
      events: [
        { id: '1', type: 'Can', result: 'accepted', valueCents: 20, createdAt: new Date().toISOString() },
        { id: '2', type: 'Bottle', result: 'rejected', valueCents: 0, reason: 'Barcode could not be read', createdAt: new Date().toISOString() },
        { id: '3', type: 'Bottle', result: 'accepted', valueCents: 20, createdAt: new Date().toISOString() },
      ],
    }
    expect(getSessionTotal(session)).toBe(40)
    expect(formatMoney(getSessionTotal(session))).toBe('RM0.40')
  })
})

describe('disposal guidance', () => {
  it('matches everyday item descriptions to broad waste streams', () => {
    expect(classifyDisposal('a broken mobile phone')?.id).toBe('electronics')
    expect(classifyDisposal('an old household battery')?.id).toBe('hazardous')
    expect(classifyDisposal('glass bottle')?.id).toBe('recycling')
  })

  it('returns no confident match for an unknown description', () => {
    expect(classifyDisposal('mystery composite object')).toBeNull()
  })
})
