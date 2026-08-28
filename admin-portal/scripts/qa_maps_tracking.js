const path = require("path");
const { chromium } = require("playwright");

async function visibleMapFrame(page) {
  const iframe = page.locator("iframe:visible").first();
  await iframe.waitFor({ state: "visible", timeout: 180000 });
  const handle = await iframe.elementHandle();
  const frame = await handle.contentFrame();
  await frame.locator(".leaflet-container").waitFor({ timeout: 180000 });
  return frame;
}

async function trackingMapFrame(page) {
  const deadline = Date.now() + 180000;
  while (Date.now() < deadline) {
    const handles = await page.locator("iframe").elementHandles();
    for (const handle of handles) {
      const frame = await handle.contentFrame();
      if (frame && (await frame.locator(".dispatch-panel").count()) > 0) return frame;
    }
    await page.waitForTimeout(100);
  }
  throw new Error("Tracking map frame was not found");
}

async function mapContract(frame) {
  return frame.evaluate(async () => {
    const map = Object.values(window).find(
      (value) => window.L && value instanceof window.L.Map
    );
    if (!map) throw new Error("Leaflet map instance not found");
    const bounds =
      map.options.maxBounds instanceof window.L.LatLngBounds
        ? map.options.maxBounds
        : window.L.latLngBounds(map.options.maxBounds);
    if (!bounds || !bounds.isValid()) throw new Error("Valid maximum map bounds not found");
    const southWest = bounds.getSouthWest();
    const northEast = bounds.getNorthEast();
    const insideBounds = (lat, lng) =>
      Number.isFinite(lat) &&
      Number.isFinite(lng) &&
      lat >= southWest.lat &&
      lat <= northEast.lat &&
      lng >= southWest.lng &&
      lng <= northEast.lng;
    let noWrap = false;
    let routeInsideBounds = true;
    function checkLatLngs(value) {
      if (Array.isArray(value)) {
        value.forEach(checkLatLngs);
      } else if (value && ("lat" in value || "lng" in value)) {
        const validPoint = Number.isFinite(value.lat) && Number.isFinite(value.lng);
        routeInsideBounds =
          routeInsideBounds && validPoint && insideBounds(value.lat, value.lng);
      }
    }
    map.eachLayer((layer) => {
      if (layer instanceof window.L.TileLayer) noWrap ||= layer.options.noWrap === true;
      if (layer instanceof window.L.Polyline) checkLatLngs(layer.getLatLngs());
    });
    map.setView([0, 0], map.getMinZoom() - 3, { animate: false });
    await new Promise((resolve) => setTimeout(resolve, 80));
    return {
      minZoom: map.getMinZoom(),
      maxZoom: map.getMaxZoom(),
      zoomAfterForcedZoomOut: map.getZoom(),
      maxBoundsViscosity: map.options.maxBoundsViscosity,
      noWrap,
      forcedOutsideCenterContained: insideBounds(map.getCenter().lat, map.getCenter().lng),
      routeInsideBounds,
      resetControlCount: document.querySelectorAll(".binsight-reset").length,
      siteMarkerCount: document.querySelectorAll(".binsight-site-marker").length,
      recyclingFacilityCount: document.querySelectorAll('[aria-label="Recycling facility"]').length,
      iframeNoHorizontalOverflow:
        document.documentElement.scrollWidth <= window.innerWidth + 1,
    };
  });
}

async function main() {
  const outputDir = process.argv[2];
  if (!outputDir) throw new Error("Usage: node qa_maps_tracking.js OUTPUT_DIR");
  const launchOptions = { headless: true };
  if (process.env.BROWSER_EXECUTABLE) launchOptions.executablePath = process.env.BROWSER_EXECUTABLE;
  const browser = await chromium.launch(launchOptions);
  const pageErrors = [];
  const consoleErrors = [];
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await context.newPage();
    page.on("pageerror", (error) => pageErrors.push(error.stack || error.message));
    page.on("console", (message) => {
      if (message.type() === "error") consoleErrors.push(message.text());
    });
    await page.goto(process.env.DASHBOARD_URL || "http://127.0.0.1:8501", {
      waitUntil: "domcontentloaded",
      timeout: 180000,
    });
    await page.getByRole("tab", { name: "Operations" }).waitFor({ timeout: 180000 });
    await page.getByRole("tab", { name: "Operations" }).click();
    const operationsFrame = await visibleMapFrame(page);
    const operationsContract = await mapContract(operationsFrame);
    await operationsFrame.locator(".binsight-site-marker").first().click();
    const popupRows = await operationsFrame.locator(".site-popup tbody tr").count();
    const popupText = await operationsFrame.locator(".site-popup").innerText();
    const stateTokens = await operationsFrame.locator(".binsight-site-marker").evaluateAll(
      (elements) => [...new Set(elements.map((element) => element.dataset.state))]
    );
    await page.screenshot({
      path: path.join(outputDir, "bounded-consolidated-operations.png"),
      fullPage: true,
      timeout: 180000,
    });

    await page.getByRole("tab", { name: "Mock live tracking" }).click();
    const trackingFrame = await trackingMapFrame(page);
    await trackingFrame.locator(".dispatch-panel").waitFor();
    const trackingContract = await mapContract(trackingFrame);
    const truck = trackingFrame.locator(".truck-icon");
    await truck.waitFor();
    const before = await trackingFrame.evaluate(() => ({
      minute: window.binsightTracking.getSimulationMinute(),
      position: window.binsightTracking.getTruckPosition(),
    }));
    await trackingFrame.getByRole("button", { name: "Resume" }).click();
    await trackingFrame.waitForTimeout(900);
    const after = await trackingFrame.evaluate(() => ({
      minute: window.binsightTracking.getSimulationMinute(),
      position: window.binsightTracking.getTruckPosition(),
    }));
    const runningStatus = await trackingFrame.locator('[data-field="status"]').innerText();
    await trackingFrame.getByRole("button", { name: "Pause" }).click();
    const pauseStatus = await trackingFrame.locator('[data-field="status"]').innerText();
    const completionState = await trackingFrame.evaluate(() => {
      const entries = Object.entries(window.binsightTracking.manifest.site_completion_minutes);
      const [siteId, completeAt] = entries[0];
      const marker = document.querySelector(`.binsight-site-marker[data-site-id="${siteId}"]`);
      const originalSymbol = marker.dataset.originalSymbol;
      window.binsightTracking.setSimulationMinute(completeAt - 0.001);
      const beforeComplete = {
        serviced: marker.dataset.serviced,
        fillLevel: marker.style.getPropertyValue("--fill-level"),
        badge: marker.querySelector(".site-badge").textContent,
        symbol: marker.querySelector(".site-symbol").textContent,
      };
      window.binsightTracking.setSimulationMinute(completeAt + 0.001);
      const afterComplete = {
        serviced: marker.dataset.serviced,
        fillLevel: marker.style.getPropertyValue("--fill-level"),
        badge: marker.querySelector(".site-badge").textContent,
        symbol: marker.querySelector(".site-symbol").textContent,
      };
      window.binsightTracking.setSimulationMinute(window.binsightTracking.manifest.start_minute);
      const afterReset = {
        serviced: marker.dataset.serviced,
        symbol: marker.querySelector(".site-symbol").textContent,
      };
      return { siteId, originalSymbol, beforeComplete, afterComplete, afterReset };
    });
    const fillGauge = await trackingFrame.evaluate(() => {
      const markers = [...document.querySelectorAll(".binsight-site-marker.tracking-fill")];
      return {
        markerCount: markers.length,
        levels: markers.map((marker) => marker.style.getPropertyValue("--fill-level")),
        colors: markers.map((marker) => marker.style.getPropertyValue("--fill-color")),
      };
    });
    const routeContinuity = await trackingFrame.evaluate(() => {
      const segments = window.binsightTracking.manifest.segments;
      const distanceM = (first, second) => {
        const radius = 6371008.8;
        const radians = (value) => value * Math.PI / 180;
        const lat1 = radians(first[0]);
        const lat2 = radians(second[0]);
        const dLat = radians(second[0] - first[0]);
        const dLon = radians(second[1] - first[1]);
        const a = Math.sin(dLat / 2) ** 2 +
          Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
        return 2 * radius * Math.asin(Math.sqrt(a));
      };
      const transitions = segments.slice(1).map((segment, index) => {
        const previous = segments[index];
        return distanceM(previous.geometry[previous.geometry.length - 1], segment.geometry[0]);
      });
      const sj9ToSj8 = segments.find(
        (segment) => segment.kind === "travel" && segment.next_stop === "UGB-029"
      );
      return {
        maxTransitionGapM: Math.max(0, ...transitions),
        sj9ToSj8Start: sj9ToSj8?.geometry[0],
        sj9ToSj8End: sj9ToSj8?.geometry[sj9ToSj8.geometry.length - 1],
      };
    });
    await page.screenshot({
      path: path.join(outputDir, "mock-live-tracking-desktop.png"),
      fullPage: true,
      timeout: 180000,
    });

    const responsive = {};
    for (const [name, viewport] of Object.entries({
      tablet: { width: 768, height: 1024 },
      mobile: { width: 390, height: 844 },
    })) {
      const target = await context.newPage();
      await target.setViewportSize(viewport);
      await target.goto(process.env.DASHBOARD_URL || "http://127.0.0.1:8501", {
        waitUntil: "domcontentloaded",
        timeout: 180000,
      });
      await target.getByRole("tab", { name: "Mock live tracking" }).waitFor({ timeout: 180000 });
      await target.getByRole("tab", { name: "Mock live tracking" }).click();
      const frame = await trackingMapFrame(target);
      responsive[name] = {
        pageNoHorizontalOverflow: await target.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth + 1
        ),
        mapNoHorizontalOverflow: await frame.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth + 1
        ),
        siteMarkerCount: await frame.locator(".binsight-site-marker").count(),
      };
      await target.screenshot({
        path: path.join(outputDir, `mock-live-tracking-${name}.png`),
        fullPage: true,
        timeout: 180000,
      });
      await target.close();
    }

    const reducedContext = await browser.newContext({
      viewport: { width: 390, height: 844 },
      reducedMotion: "reduce",
    });
    const reduced = await reducedContext.newPage();
    await reduced.goto(process.env.DASHBOARD_URL || "http://127.0.0.1:8501", {
      waitUntil: "domcontentloaded",
      timeout: 180000,
    });
    await reduced.getByRole("tab", { name: "Mock live tracking" }).waitFor({ timeout: 180000 });
    await reduced.getByRole("tab", { name: "Mock live tracking" }).click();
    const reducedFrame = await trackingMapFrame(reduced);
    await reducedFrame.locator(".truck-icon").waitFor({ timeout: 180000 });
    const reducedMotion = await reducedFrame.evaluate(() => {
      const element = document.querySelector(".truck-icon");
      const pseudo = getComputedStyle(element, "::before");
      return {
        mediaMatches: matchMedia("(prefers-reduced-motion: reduce)").matches,
        pulseDisplay: pseudo.display,
        pulseAnimation: pseudo.animationName,
      };
    });
    await reducedContext.close();

    const result = {
      operationsContract,
      trackingContract,
      popupRows,
      popupHasFourBinIds: (popupText.match(/UGB-\d{3}/g) || []).length === 4,
      stateTokens,
      truckMovedAfterResume:
        after.minute > before.minute &&
        (after.position.lat !== before.position.lat || after.position.lng !== before.position.lng),
      runningStatus,
      pauseStatus,
      completionState,
      fillGauge,
      routeContinuity,
      responsive,
      reducedMotion,
      pageErrors,
      consoleErrors,
    };
    process.stdout.write(JSON.stringify(result, null, 2));

    const contracts = [operationsContract, trackingContract];
    const failed =
      contracts.some((item) =>
        item.siteMarkerCount !== 11 ||
        item.recyclingFacilityCount !== 1 ||
        !item.noWrap ||
        item.maxBoundsViscosity !== 1 ||
        item.zoomAfterForcedZoomOut < item.minZoom ||
        !item.forcedOutsideCenterContained ||
        !item.routeInsideBounds ||
        !item.iframeNoHorizontalOverflow
      ) ||
      popupRows !== 4 ||
      !result.popupHasFourBinIds ||
      !result.truckMovedAfterResume ||
      completionState.beforeComplete.serviced !== "false" ||
      completionState.afterComplete.serviced !== "true" ||
      completionState.afterComplete.fillLevel !== "0.0%" ||
      completionState.afterComplete.badge !== "0%" ||
      completionState.afterComplete.symbol !== completionState.originalSymbol ||
      completionState.afterReset.serviced !== "false" ||
      completionState.afterReset.symbol !== completionState.originalSymbol ||
      fillGauge.markerCount !== 11 ||
      fillGauge.levels.some((value) => !value.endsWith("%")) ||
      fillGauge.colors.some((value) => !value.startsWith("rgb(")) ||
      routeContinuity.maxTransitionGapM > 25 ||
      !routeContinuity.sj9ToSj8Start ||
      !routeContinuity.sj9ToSj8End ||
      Object.values(responsive).some(
        (item) => !item.pageNoHorizontalOverflow || !item.mapNoHorizontalOverflow || item.siteMarkerCount !== 11
      ) ||
      !reducedMotion.mediaMatches ||
      reducedMotion.pulseDisplay !== "none" ||
      pageErrors.length > 0 ||
      consoleErrors.length > 0;
    if (failed) process.exitCode = 1;
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  process.stderr.write(`${error.stack}\n`);
  process.exit(1);
});
