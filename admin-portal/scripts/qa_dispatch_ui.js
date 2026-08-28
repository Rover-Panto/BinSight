const path = require("path");
const fs = require("fs");
const { chromium } = require("playwright");

async function main() {
  const outputDir = process.argv[2];
  if (!outputDir) throw new Error("Usage: node qa_dispatch_ui.js OUTPUT_DIR");
  const dispatchLog = path.join(__dirname, "..", "data", "mock_truck_dispatches.jsonl");
  const originalDispatchLog = fs.existsSync(dispatchLog) ? fs.readFileSync(dispatchLog) : null;

  const launchOptions = { headless: true };
  if (process.env.BROWSER_EXECUTABLE) {
    launchOptions.executablePath = process.env.BROWSER_EXECUTABLE;
  }
  const browser = await chromium.launch(launchOptions);
  const consoleErrors = [];
  const pageErrors = [];
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    page.on("console", (message) => {
      if (message.type() === "error") consoleErrors.push(message.text());
    });
    page.on("pageerror", (error) => pageErrors.push(error.message));

    await page.goto(process.env.DASHBOARD_URL || "http://127.0.0.1:8501", {
      waitUntil: "domcontentloaded",
      timeout: 180000,
    });
    await page.getByRole("tab", { name: "Routing demo" }).waitFor({ timeout: 180000 });
    await page.getByText("Run the demonstration route", { exact: true }).waitFor({ timeout: 180000 });
    await page.screenshot({ path: path.join(outputDir, "route-input-desktop.png"), fullPage: true });
    await page.getByText("Demonstration ready", { exact: true }).waitFor();
    await page.getByText(/UGB-001 and UGB-005 are the early-departure example/).waitFor();
    await page.getByRole("button", { name: "Run demonstration and build collection route" }).click();

    await page.getByText("Bin collection required", { exact: true }).waitFor({ timeout: 180000 });
    await page.getByRole("button", { name: "Send mock route to garbage truck" }).waitFor();
    const sendDisabledBeforeApproval = await page
      .getByRole("button", { name: "Send mock route to garbage truck" })
      .isDisabled();
    const routeFrames = await page.locator("iframe").count();
    await page.screenshot({ path: path.join(outputDir, "collection-required.png"), fullPage: true });

    await page.getByRole("button", { name: "Approve route proposal" }).click();
    await page.getByText(/lifecycle ACCEPTED/).waitFor({ timeout: 30000 });
    const sendEnabledAfterApproval = await page
      .getByRole("button", { name: "Send mock route to garbage truck" })
      .isEnabled();
    await page.getByRole("button", { name: "Send mock route to garbage truck" }).click();
    await page.getByText(/Mock route (recorded|already recorded) for .*GENERAL-01|Mock route (recorded|already recorded) for .*RECYCLING-01/).waitFor({ timeout: 30000 });
    const successText = await page.getByText(/Mock route (recorded|already recorded) for/).first().innerText();
    await page.screenshot({ path: path.join(outputDir, "mock-dispatch-sent.png"), fullPage: true });

    await page.getByRole("tab", { name: "Dispatch log" }).click();
    await page.getByText("Plans and mock dispatch records", { exact: true }).waitFor();
    await page.getByRole("button", { name: "Download latest dispatch JSON" }).waitFor();
    await page.screenshot({ path: path.join(outputDir, "mock-dispatch-log.png"), fullPage: true });

    await page.getByRole("tab", { name: "Operations" }).click();
    await page.getByText("Overflow change", { exact: true }).waitFor();
    await page.screenshot({ path: path.join(outputDir, "operations-desktop.png"), fullPage: true });

    const tablet = await browser.newPage({ viewport: { width: 768, height: 1024 } });
    await tablet.goto(process.env.DASHBOARD_URL || "http://127.0.0.1:8501", {
      waitUntil: "domcontentloaded",
      timeout: 180000,
    });
    await tablet.getByRole("tab", { name: "Routing demo" }).waitFor({ timeout: 180000 });
    await tablet.getByText("Run the demonstration route", { exact: true }).waitFor({ timeout: 180000 });
    await tablet.screenshot({ path: path.join(outputDir, "route-input-tablet.png"), fullPage: true });

    const mobile = await browser.newPage({ viewport: { width: 390, height: 844 } });
    mobile.on("console", (message) => {
      if (message.type() === "error") consoleErrors.push(`[mobile] ${message.text()}`);
    });
    mobile.on("pageerror", (error) => pageErrors.push(`[mobile] ${error.message}`));
    await mobile.goto(process.env.DASHBOARD_URL || "http://127.0.0.1:8501", {
      waitUntil: "domcontentloaded",
      timeout: 180000,
    });
    await mobile.getByRole("tab", { name: "Routing demo" }).waitFor({ timeout: 180000 });
    await mobile.getByText("Run the demonstration route", { exact: true }).waitFor({ timeout: 180000 });
    await mobile.screenshot({ path: path.join(outputDir, "route-input-mobile.png"), fullPage: true });

    const viewportChecks = {};
    for (const [name, target] of [["desktop", page], ["tablet", tablet], ["mobile", mobile]]) {
      viewportChecks[name] = await target.evaluate(() => ({
        viewportWidth: window.innerWidth,
        scrollWidth: document.documentElement.scrollWidth,
        noHorizontalOverflow: document.documentElement.scrollWidth <= window.innerWidth + 1,
      }));
    }

    process.stdout.write(JSON.stringify({
      routeFrames,
      sendDisabledBeforeApproval,
      sendEnabledAfterApproval,
      successText,
      consoleErrors,
      pageErrors,
      checks: {
        overviewLoaded: true,
        demoSelected: true,
        collectionDecisionShown: true,
        lifecycleApprovalRequired: sendDisabledBeforeApproval && sendEnabledAfterApproval,
        mockDispatchSent: true,
        auditLogShown: true,
        tabletLoaded: true,
        mobileLoaded: true,
      },
      viewportChecks,
    }, null, 2));
  } finally {
    await browser.close();
    if (originalDispatchLog === null) {
      if (fs.existsSync(dispatchLog)) fs.unlinkSync(dispatchLog);
    } else {
      fs.writeFileSync(dispatchLog, originalDispatchLog);
    }
  }
}

main().catch((error) => {
  process.stderr.write(`${error.stack}\n`);
  process.exit(1);
});
