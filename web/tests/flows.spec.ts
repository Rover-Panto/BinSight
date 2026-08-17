import { expect, test, type Page } from '@playwright/test'

async function login(page: Page) {
  await page.goto('/login')
  await page.getByLabel('National ID').fill('DEMO-MY-2468')
  await page.getByRole('button', { name: /send mock otp/i }).click()
  const digits = ['1', '2', '3', '4', '5', '6']
  for (let index = 0; index < digits.length; index += 1) {
    await page.getByLabel(`OTP digit ${index + 1}`).fill(digits[index])
  }
  await page.getByRole('button', { name: /verify and continue/i }).click()
  await expect(page.getByRole('heading', { name: /good afternoon/i })).toBeVisible()
}

test('resident completes a two-item return and simulated payout', async ({ page }) => {
  await login(page)
  await page.getByRole('button', { name: /start return/i }).click()
  await expect(page.getByText('No items added yet')).toBeVisible()

  await page.getByRole('button', { name: /^add item$/i }).first().click()
  await page.getByRole('button', { name: /add can/i }).click()
  await expect(page.getByText('Can accepted · +RM0.20')).toBeVisible()

  await page.getByRole('button', { name: /add another item/i }).click()
  await page.getByText('Bottle', { exact: true }).click()
  await page.getByRole('button', { name: /add bottle/i }).click()
  await expect(page.getByText('Bottle accepted · +RM0.20')).toBeVisible()

  await page.getByRole('button', { name: /finish return/i }).first().click()
  await expect(page.getByRole('heading', { name: /choose payout method/i })).toBeVisible()
  await page.getByRole('button', { name: /send rm0.40/i }).click()
  await expect(page.getByRole('heading', { name: /rm0.40 sent/i })).toBeVisible()
  await expect(page.getByText(/no funds were transferred/i)).toBeVisible()
})

test('resident submits and tracks a waste issue', async ({ page }) => {
  await login(page)
  await page.getByRole('link', { name: /report/i }).first().click()
  await page.getByLabel('Category').selectOption('Illegal dumping or litter')
  await page.getByLabel('Issue location').fill('Jalan Universiti bus stop, Petaling Jaya')
  await page.getByLabel('Description').fill('Several bags of household waste were left beside the public recycling point and are blocking access.')
  await page.getByRole('button', { name: /submit report/i }).click()
  await expect(page.getByText('Submitted', { exact: true }).first()).toBeVisible()
  await expect(page.getByText('Illegal dumping or litter')).toBeVisible()
  await expect(page.getByText('Jalan Universiti bus stop, Petaling Jaya')).toBeVisible()
})
