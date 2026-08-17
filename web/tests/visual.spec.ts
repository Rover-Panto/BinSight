import { expect, test, type Page } from '@playwright/test'

async function login(page: Page) {
  await page.goto('/login')
  await page.getByLabel('National ID').fill('VISUAL-DEMO-01')
  await page.getByRole('button', { name: /send mock otp/i }).click()
  for (const [index, digit] of ['1', '2', '3', '4', '5', '6'].entries()) {
    await page.getByLabel(`OTP digit ${index + 1}`).fill(digit)
  }
  await page.getByRole('button', { name: /verify and continue/i }).click()
  await expect(page.getByRole('heading', { name: /dispose, return or report/i })).toBeVisible()
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

  await page.goto('/guide?q=broken%20phone')
  await expectNoHorizontalOverflow(page)
  await page.screenshot({ path: 'test-results/visual/disposal-desktop.png' })

  await page.goto('/account')
  await expectNoHorizontalOverflow(page)
  await page.screenshot({ path: 'test-results/visual/account-desktop.png' })
  await page.locator('.local-server-panel').scrollIntoViewIfNeeded()
  await page.locator('.local-server-panel').screenshot({ path: 'test-results/visual/server-control-desktop.png' })

  await page.goto('/report')
  await page.getByLabel('Category').selectOption('Overflowing public bin')
  await page.getByLabel('Issue location').fill('Visual review location, Petaling Jaya')
  await page.getByLabel('Description').fill('Visual review report with a locally stored image attachment for layout verification.')
  await page.locator('input[type="file"]').setInputFiles('public/images/binsight-smart-station.webp')
  await expect(page.getByAltText('Preview of binsight-smart-station.webp')).toBeVisible()
  await page.getByRole('button', { name: /submit report/i }).click()
  await expect(page.getByAltText('Report attachment binsight-smart-station.webp')).toBeVisible()
  await expectNoHorizontalOverflow(page)
  await page.screenshot({ path: 'test-results/visual/report-attachment-desktop.png' })

  await page.setViewportSize({ width: 768, height: 1024 })
  await page.goto('/')
  await expectNoHorizontalOverflow(page)
  await page.screenshot({ path: 'test-results/visual/home-tablet.png' })

  await page.setViewportSize({ width: 390, height: 844 })
  await page.reload()
  await expectNoHorizontalOverflow(page)
  await page.screenshot({ path: 'test-results/visual/home-mobile.png' })

  await page.getByRole('button', { name: /return a container/i }).click()
  await expectNoHorizontalOverflow(page)
  await page.screenshot({ path: 'test-results/visual/return-mobile.png' })

  await page.goto('/report')
  await expectNoHorizontalOverflow(page)
  await page.screenshot({ path: 'test-results/visual/report-mobile.png' })

  await page.goto('/guide?q=broken%20phone')
  await expectNoHorizontalOverflow(page)
  await page.screenshot({ path: 'test-results/visual/disposal-mobile.png' })
})
