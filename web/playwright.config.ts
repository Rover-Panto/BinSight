import { defineConfig, devices } from '@playwright/test'

const localChrome = process.env.PLAYWRIGHT_CHROME_PATH
  ? { launchOptions: { executablePath: process.env.PLAYWRIGHT_CHROME_PATH } }
  : {}

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  timeout: 30_000,
  expect: { timeout: 7_000 },
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:4173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'], ...localChrome, viewport: { width: 1440, height: 900 } } },
    { name: 'mobile', use: { ...devices['Pixel 7'], ...localChrome, viewport: { width: 390, height: 844 } } },
  ],
  webServer: {
    command: 'node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 4173',
    url: 'http://127.0.0.1:4173',
    reuseExistingServer: true,
  },
})
