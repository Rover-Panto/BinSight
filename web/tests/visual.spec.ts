import { expect, test, type Page } from '@playwright/test'

async function login(page: Page) {
  await page.goto('/login')
  await page.getByLabel('National ID').fill('VISUAL-DEMO-01')
  await page.getByRole('button', { name: /send mock otp/i }).click()
  for (const [index, digit] of ['1', '2', '3', '4', '5', '6'].entries()) {
    await page.getByLabel(`OTP digit ${index + 1}`).fill(digit)
  }
  await page.getByRole('button', { name: /verify and continue/i }).click()
  await expect(page.getByRole('heading', { name: /good afternoon/i })).toBeVisible()
}

async function expectNoHorizontalOverflow(page: Page) {
  const dimensions = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    content: document.documentElement.scrollWidth,
  }))
  expect(dimensions.content).toBeLessThanOrEqual(dimensions.viewport + 1)
}

test('captures responsive visual QA surfaces', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop', 'One Chromium project captures all required viewport sizes.')
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/login')
  await expectNoHorizontalOverflow(page)
  await page.screenshot({ path: 'test-results/visual/login-desktop.png' })

  await login(page)
  await expectNoHorizontalOverflow(page)
  await page.screenshot({ path: 'test-results/visual/home-desktop.png' })

  await page.setViewportSize({ width: 768, height: 1024 })
  await page.reload()
  await expectNoHorizontalOverflow(page)
  await page.screenshot({ path: 'test-results/visual/home-tablet.png' })

  await page.setViewportSize({ width: 390, height: 844 })
  await page.reload()
  await expectNoHorizontalOverflow(page)
  await page.screenshot({ path: 'test-results/visual/home-mobile.png' })

  await page.getByRole('button', { name: /start return/i }).click()
  await expectNoHorizontalOverflow(page)
  await page.screenshot({ path: 'test-results/visual/return-mobile.png' })

  await page.goto('/report')
  await expectNoHorizontalOverflow(page)
  await page.screenshot({ path: 'test-results/visual/report-mobile.png' })
})
