const path = require("path");
const { chromium } = require("playwright");

async function fleetFrame(page) {
  const deadline = Date.now() + 180000;
  while (Date.now() < deadline) {
    const handles = await page.locator("iframe").elementHandles();
    for (const handle of handles) {
      const frame = await handle.contentFrame();
      if (frame && (await frame.locator(".fleet-panel").count()) > 0) return frame;
    }
    await page.waitForTimeout(100);
  }
  throw new Error("Monthly fleet playback frame was not found");
}

async function selectDay(page, day) {
  const combo = page.getByRole("combobox", { name: "Simulation day" });
  await combo.click();
  await page.getByRole("option", { name: new RegExp(`Day ${String(day).padStart(2, "0")}`) }).click();
}

async function main() {
  const outputDir = process.argv[2];
  if (!outputDir) throw new Error("Usage: node qa_monthly_playback.js OUTPUT_DIR");
  const launchOptions = { headless: true };
  if (process.env.BROWSER_EXECUTABLE) launchOptions.executablePath = process.env.BROWSER_EXECUTABLE;
  const browser = await chromium.launch(launchOptions);
  const pageErrors = [];
  const consoleErrors = [];
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    page.on("pageerror", (error) => pageErrors.push(error.stack || error.message));
    page.on("console", (message) => {
      if (message.type() === "error") consoleErrors.push(message.text());
    });
    const baseUrl = process.env.DASHBOARD_URL || "http://127.0.0.1:8501";
    await page.goto(baseUrl, { waitUntil: "domcontentloaded", timeout: 180000 });
    const openPlayback = page.getByRole("button", { name: "Run 30-day experiment" });
    await openPlayback.waitFor({ timeout: 180000 });
    await openPlayback.click();
    await page.getByRole("heading", { name: "Two trucks. One month. Any day." }).waitFor({ timeout: 180000 });
    if (!page.url().includes("view=fleet-playback")) throw new Error("Playback navigation did not set the dedicated view");

    let frame = await fleetFrame(page);
    const activeState = await frame.evaluate(() => {
      const playback = window.binsightFleetPlayback;
      const base = playback.getTruckPositions();
      const starts = playback.manifest.vehicles
        .flatMap((vehicle) => vehicle.segments)
        .filter((segment) => segment.kind === "travel")
        .map((segment) => segment.start_minute);
      playback.setSimulationMinute(Math.min(...starts) + 1);
      return {
        day: playback.manifest.day,
        vehicleIds: playback.manifest.vehicles.map((vehicle) => vehicle.vehicle_id),
        tripCounts: playback.manifest.vehicles.map((vehicle) => vehicle.trip_count),
        base,
        moved: playback.getTruckPositions(),
        markerCount: document.querySelectorAll(".fleet-truck-marker").length,
        siteCount: document.querySelectorAll(".fleet-site-dot").length,
      };
    });
    await frame.getByLabel("Playback speed").selectOption("240");
    await frame.getByRole("button", { name: "Resume" }).click();
    await frame.waitForTimeout(650);
    const advancedMinute = await frame.evaluate(() => window.binsightFleetPlayback.getSimulationMinute());
    await frame.getByRole("button", { name: "Pause" }).click();
    await page.screenshot({ path: path.join(outputDir, "monthly-fleet-day-04.png"), fullPage: true });

    await selectDay(page, 1);
    await page.getByText(/Day 01 has no collection route/).waitFor({ timeout: 180000 });
    frame = await fleetFrame(page);
    const idleState = await frame.evaluate(() => ({
      day: window.binsightFleetPlayback.manifest.day,
      hasDispatch: window.binsightFleetPlayback.manifest.has_dispatch,
      vehicleIds: window.binsightFleetPlayback.manifest.vehicles.map((vehicle) => vehicle.vehicle_id),
      positions: window.binsightFleetPlayback.getTruckPositions(),
      bases: Object.fromEntries(window.binsightFleetPlayback.manifest.vehicles.map((vehicle) => [vehicle.vehicle_id, vehicle.base_coordinate])),
      markerCount: document.querySelectorAll(".fleet-truck-marker").length,
    }));
    await page.screenshot({ path: path.join(outputDir, "monthly-fleet-day-01-idle.png"), fullPage: true });

    const movedDistance = (first, second) => Math.hypot(first.lat - second.lat, first.lng - second.lng);
    const bothMoved = activeState.vehicleIds.every(
      (vehicleId) => movedDistance(activeState.base[vehicleId], activeState.moved[vehicleId]) > 1e-7
    );
    const bothIdleAtBase = idleState.vehicleIds.every((vehicleId) => {
      const position = idleState.positions[vehicleId];
      const base = idleState.bases[vehicleId];
      return Math.hypot(position.lat - base[0], position.lng - base[1]) < 1e-10;
    });
    const result = {
      activeState,
      advancedMinute,
      idleState,
      pageErrors,
      consoleErrors,
      checks: {
        dedicatedNavigation: page.url().includes("view=fleet-playback"),
        twoSpecializedTrucks: activeState.vehicleIds.join(",") === "GENERAL-01,RECYCLING-01",
        bothTrucksMoveTogether: bothMoved,
        twoMapMarkers: activeState.markerCount === 2 && idleState.markerCount === 2,
        elevenSites: activeState.siteCount === 11,
        speedControlAdvances: advancedMinute > 4321,
        idleDayAvailable: idleState.day === 1 && idleState.hasDispatch === false,
        idleTrucksAtCorrectBases: bothIdleAtBase,
      },
    };
    process.stdout.write(JSON.stringify(result, null, 2));
    if (
      Object.values(result.checks).some((value) => !value) ||
      pageErrors.length ||
      consoleErrors.length
    ) process.exitCode = 1;
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  process.stderr.write(`${error.stack}\n`);
  process.exit(1);
});
