import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from './App'
import { createDefaultData } from './model'
import { StoreProvider } from './store'

const renderApp = (route: string) => render(
  <MemoryRouter initialEntries={[route]}>
    <StoreProvider><App /></StoreProvider>
  </MemoryRouter>,
)

describe('BinSight frontend', () => {
  it('logs in with the mock OTP and persists only generated authentication data', async () => {
    const user = userEvent.setup()
    renderApp('/login')
    await user.type(screen.getByLabelText('National ID'), 'DEMO123456')
    await user.click(screen.getByRole('button', { name: /send mock otp/i }))
    for (let index = 1; index <= 6; index += 1) {
      await user.type(screen.getByLabelText(`OTP digit ${index}`), String(index))
    }
    await user.click(screen.getByRole('button', { name: /verify and continue/i }))
    expect(await screen.findByRole('heading', { name: /good afternoon/i })).toBeInTheDocument()
    const stored = localStorage.getItem('binsight-demo-v1') ?? ''
    expect(stored).toContain('authenticated')
    expect(stored).not.toContain('DEMO123456')
    expect(stored).not.toContain('123456')
  })

  it('keeps rejected items out of the payout and offers another item', async () => {
    const data = createDefaultData()
    data.auth = { authenticated: true, userId: 'demo-test' }
    data.settings.nextItemOutcome = 'rejected'
    data.settings.rejectedReason = 'Barcode could not be read'
    data.returns.unshift({ id: 'BS-TEST', status: 'active', events: [], createdAt: new Date().toISOString() })
    localStorage.setItem('binsight-demo-v1', JSON.stringify(data))
    const user = userEvent.setup()
    renderApp('/return/BS-TEST')
    await user.click(screen.getAllByRole('button', { name: /^add item$/i })[0])
    await user.click(screen.getByRole('button', { name: /add can/i }))
    expect(await screen.findByRole('heading', { name: /barcode could not be read/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /add another item/i })).toBeInTheDocument()
    expect(screen.getAllByText('RM0.00').length).toBeGreaterThan(0)
  })
})
