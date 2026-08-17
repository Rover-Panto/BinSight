const path = require("path");
const { chromium } = require("playwright");

async function main() {
  const output = process.argv[2];
  if (!output) {
    throw new Error("Usage: node capture_route_map.js OUTPUT.png");
  }
  const launchOptions = { headless: true };
  if (process.env.BROWSER_EXECUTABLE) {
    launchOptions.executablePath = process.env.BROWSER_EXECUTABLE;
  }
  const browser = await chromium.launch(launchOptions);
  try {
    const page = await browser.newPage({
      viewport: { width: 1600, height: 1050 },
      deviceScaleFactor: 1.5,
    });
    await page.goto(process.env.DASHBOARD_URL || "http://127.0.0.1:8765", {
      waitUntil: "domcontentloaded",
      timeout: 180000,
    });
    const operationsTab = page.getByRole("tab", { name: "Operations" });
    await operationsTab.waitFor({ timeout: 180000 });
    await operationsTab.click();
    const mapFrame = page.locator("iframe:visible").first();
    await mapFrame.waitFor({ state: "visible", timeout: 180000 });
    await page.waitForTimeout(8000);
    await mapFrame.screenshot({ path: path.resolve(output) });
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  process.stderr.write(`${error.stack}\n`);
  process.exit(1);
});
