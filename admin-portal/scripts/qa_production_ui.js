const path = require("path");
const { chromium } = require("playwright");

async function main() {
  const outputDir = process.argv[2];
  if (!outputDir) throw new Error("Usage: node qa_production_ui.js OUTPUT_DIR");
  const launchOptions = { headless: true };
  if (process.env.BROWSER_EXECUTABLE) launchOptions.executablePath = process.env.BROWSER_EXECUTABLE;
  const browser = await chromium.launch(launchOptions);
  const pageErrors = [];
  const consoleErrors = [];
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
    page.on("pageerror", (error) => pageErrors.push(error.stack || error.message));
    page.on("console", (message) => {
      if (message.type() === "error") consoleErrors.push(message.text());
    });
    await page.goto(process.env.DASHBOARD_URL || "http://127.0.0.1:8501", {
      waitUntil: "domcontentloaded",
      timeout: 180000,
    });
    await page.getByRole("tab", { name: "Routing demo" }).waitFor({ timeout: 180000 });
    await page.getByText("Run the demonstration route", { exact: true }).waitFor();
    await page.getByText(/supplies all 44 configured bins automatically/).waitFor();
    await page.getByText(/Preview shows 12 of 44 bins/).waitFor();
    const fileInputCount = await page.locator('input[type="file"]').count();
    await page.screenshot({ path: path.join(outputDir, "four-bin-demo-ready.png"), fullPage: true });

    await page.getByRole("button", { name: "Run demonstration and build collection route" }).click();
    await page.getByText("Bin collection required", { exact: true }).waitFor({ timeout: 180000 });
    await page.getByText("Dispatch route preview", { exact: true }).waitFor();
    await page.getByText(/USJ 9 RECYCLING/).waitFor();
    const frameHandle = await page.locator("iframe:visible").first().elementHandle();
    const frame = await frameHandle.contentFrame();
    await frame.locator(".leaflet-container").waitFor({ timeout: 180000 });
    await frame.locator('[aria-label="Recycling facility"]').waitFor();
    await frame.waitForTimeout(1500);
    const mapState = await frame.evaluate(() => ({
      siteMarkers: document.querySelectorAll(".binsight-site-marker").length,
      recyclingFacilities: document.querySelectorAll('[aria-label="Recycling facility"]').length,
      loadedTiles: document.querySelectorAll("img.leaflet-tile-loaded").length,
      background: getComputedStyle(document.querySelector(".leaflet-container")).backgroundColor,
      noApiKeyLayer: document.body.innerText.includes("no API key"),
    }));
    await frame.locator(".leaflet-container").screenshot({
      path: path.join(outputDir, "recycling-route-map.png"),
    });
    await page.screenshot({ path: path.join(outputDir, "four-bin-recycling-route.png"), fullPage: true });

    const result = {
      fileInputCount,
      mapState,
      pageErrors,
      consoleErrors,
      checks: {
        demoUses44Bins: true,
        manualUploadRemoved: fileInputCount === 0,
        routeBuilt: true,
        recyclingDestinationShown: true,
        fourBinSitesShown: mapState.siteMarkers === 11,
        facilityMarked: mapState.recyclingFacilities === 1,
        basemapLoaded: mapState.loadedTiles > 0,
      },
    };
    process.stdout.write(JSON.stringify(result, null, 2));
    if (
      fileInputCount !== 0 ||
      mapState.siteMarkers !== 11 ||
      mapState.recyclingFacilities !== 1 ||
      mapState.loadedTiles < 1 ||
      pageErrors.length ||
      consoleErrors.length
    ) {
      process.exitCode = 1;
    }
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  process.stderr.write(`${error.stack}\n`);
  process.exit(1);
});
