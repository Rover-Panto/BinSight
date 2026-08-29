const pptxgen = require("pptxgenjs");
const fs = require("fs");
const path = require("path");

const pptx = new pptxgen();
pptx.layout = "LAYOUT_WIDE";
pptx.author = "BinSight";
pptx.company = "BinSight";
pptx.subject = "How the BinSight routing decision system works after a telemetry snapshot arrives";
pptx.title = "BinSight Routing — From Snapshot to Dispatch";
pptx.lang = "en-MY";
pptx.theme = {
  headFontFace: "Calibri",
  bodyFontFace: "Calibri",
  lang: "en-MY",
};
pptx.defineSlideMaster({
  title: "CONTENT",
  background: { color: "F3F5F3" },
  objects: [],
  slideNumber: { x: 12.55, y: 7.08, w: 0.28, h: 0.18, color: "5F6B70", fontFace: "Calibri", fontSize: 9, align: "right", margin: 0 },
});

const C = {
  blue: "006DAE",
  darkBlue: "00527F",
  cyan: "21C7F6",
  graphite: "171D20",
  graphite2: "242C30",
  concrete: "F3F5F3",
  paper: "FFFFFF",
  steel: "D7DDDC",
  darkSteel: "AAB5B4",
  text: "172126",
  muted: "5F6B70",
  green: "2F7D5B",
  softGreen: "E7F2EC",
  teal: "287F83",
  softTeal: "E3F1F1",
  amber: "D99A24",
  softAmber: "FFF3DA",
  red: "C64045",
  softRed: "FBE9EA",
  paleBlue: "E7F2F8",
};

const OUT = process.env.BINSIGHT_SLIDES_OUT
  ? path.resolve(process.env.BINSIGHT_SLIDES_OUT)
  : path.resolve(__dirname, "..", "reports", "BinSight_Routing_From_Snapshot_to_Dispatch.pptx");
const EVIDENCE = path.resolve(__dirname, "..", "artifacts", "dynamic_v2", "paired_effects.csv");

function loadEvidence() {
  if (!fs.existsSync(EVIDENCE)) {
    throw new Error(`Missing matched simulation evidence: ${EVIDENCE}`);
  }
  const [headerLine, ...lines] = fs.readFileSync(EVIDENCE, "utf8").trim().split(/\r?\n/);
  const headers = headerLine.split(",");
  const rows = lines.map((line) => {
    const values = line.split(",");
    return Object.fromEntries(headers.map((header, index) => [header, values[index]]));
  });
  const normal = Object.fromEntries(
    rows
      .filter((row) => row.scenario === "normal_patterned")
      .map((row) => [row.metric, row])
  );
  const required = [
    "overflow_incidents",
    "overflow_spilled_kg",
    "distance_km",
    "collection_trips",
    "wasted_pickups",
    "fuel_l",
  ];
  required.forEach((metric) => {
    if (!normal[metric]) throw new Error(`Missing normal-patterned evidence metric: ${metric}`);
  });
  return {
    normal,
    scenarios: new Set(rows.map((row) => row.scenario)).size,
    replications: Number(normal.overflow_incidents.n_paired_replications),
  };
}

const evidence = loadEvidence();

function metricPair(metric) {
  const row = evidence.normal[metric];
  return [Number(row.fixed_mean), Number(row.smart_mean)];
}

function formatPair(metric, digits = 1, suffix = "") {
  const [fixed, dynamic] = metricPair(metric);
  return `${fixed.toFixed(digits)} → ${dynamic.toFixed(digits)}${suffix}`;
}

function shadow(opacity = 0.16, blur = 2, distance = 1, angle = 45) {
  return { type: "outer", color: "000000", opacity, blur, distance, angle };
}

function addText(slide, text, x, y, w, h, opts = {}) {
  slide.addText(text, {
    x, y, w, h,
    fontFace: "Calibri",
    fontSize: 16,
    color: C.text,
    margin: 0,
    breakLine: false,
    valign: "mid",
    fit: "shrink",
    ...opts,
  });
}

function addTitle(slide, kicker, title, subtitle = null, dark = false) {
  const main = dark ? C.paper : C.text;
  const muted = dark ? "BFD0D8" : C.muted;
  addText(slide, kicker.toUpperCase(), 0.62, 0.34, 4.9, 0.25, {
    fontSize: 10.5, bold: true, color: dark ? C.cyan : C.blue, charSpacing: 1.3,
  });
  addText(slide, title, 0.62, 0.63, 11.7, 0.58, {
    fontSize: 31, bold: true, color: main, valign: "top",
  });
  if (subtitle) {
    addText(slide, subtitle, 0.64, 1.22, 11.55, 0.42, {
      fontSize: 14, color: muted, valign: "top",
    });
  }
}

function addFooter(slide, dark = false) {
  addText(slide, "BinSight  |  routing decision support", 0.62, 7.04, 4.5, 0.18, {
    fontSize: 9, color: dark ? "9FB4BE" : C.muted,
  });
}

function addPill(slide, text, x, y, w, fill, color = C.text) {
  slide.addShape(pptx.ShapeType.roundRect, {
    x, y, w, h: 0.32,
    rectRadius: 0.07,
    fill: { color: fill },
    line: { color: fill },
  });
  addText(slide, text, x + 0.08, y + 0.01, w - 0.16, 0.29, {
    fontSize: 10.5, bold: true, color, align: "center",
  });
}

function addCard(slide, x, y, w, h, opts = {}) {
  slide.addShape(pptx.ShapeType.roundRect, {
    x, y, w, h,
    rectRadius: opts.radius || 0.08,
    fill: { color: opts.fill || C.paper, transparency: opts.transparency || 0 },
    line: { color: opts.line || C.steel, width: opts.lineWidth || 1 },
    shadow: opts.noShadow ? undefined : shadow(opts.shadowOpacity || 0.10, 1.5, 0.6, 45),
  });
}

function addNumberNode(slide, number, x, y, fill = C.blue, size = 0.48) {
  slide.addShape(pptx.ShapeType.ellipse, {
    x, y, w: size, h: size,
    fill: { color: fill },
    line: { color: fill },
  });
  addText(slide, String(number), x, y + 0.005, size, size - 0.01, {
    fontSize: 15, bold: true, color: C.paper, align: "center",
  });
}

function addArrow(slide, x1, y1, x2, y2, color = C.darkSteel, width = 2) {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const arrowAtEnd = dx > 0 || (dx === 0 && dy >= 0);
  slide.addShape(dx * dy < 0 ? pptx.ShapeType.lineInv : pptx.ShapeType.line, {
    x: Math.min(x1, x2),
    y: Math.min(y1, y2),
    w: Math.abs(dx),
    h: Math.abs(dy),
    line: {
      color,
      width,
      ...(arrowAtEnd ? { endArrowType: "triangle" } : { beginArrowType: "triangle" }),
    },
  });
}

function addLineSegment(slide, x1, y1, x2, y2, color, width, transparency = 0) {
  const dx = x2 - x1;
  const dy = y2 - y1;
  slide.addShape(dx * dy < 0 ? pptx.ShapeType.lineInv : pptx.ShapeType.line, {
    x: Math.min(x1, x2),
    y: Math.min(y1, y2),
    w: Math.abs(dx),
    h: Math.abs(dy),
    line: { color, width, transparency },
  });
}

function addRouteSchematic(slide, x, y, w, h, opts = {}) {
  slide.addShape(pptx.ShapeType.roundRect, {
    x, y, w, h,
    rectRadius: 0.08,
    fill: { color: "F7FAFA" },
    line: { color: "BFCBCD", width: 1 },
  });

  const blocks = [
    [0.05, 0.08, 0.18, 0.22, C.paleBlue],
    [0.28, 0.08, 0.24, 0.22, C.softTeal],
    [0.57, 0.08, 0.16, 0.22, C.concrete],
    [0.77, 0.08, 0.18, 0.22, C.softGreen],
    [0.05, 0.37, 0.28, 0.24, C.concrete],
    [0.38, 0.37, 0.21, 0.24, C.paleBlue],
    [0.64, 0.37, 0.31, 0.24, C.softAmber],
    [0.05, 0.68, 0.2, 0.22, C.softGreen],
    [0.3, 0.68, 0.28, 0.22, C.concrete],
    [0.63, 0.68, 0.32, 0.22, C.softTeal],
  ];
  blocks.forEach(([bx, by, bw, bh, fill]) => {
    slide.addShape(pptx.ShapeType.roundRect, {
      x: x + bx * w,
      y: y + by * h,
      w: bw * w,
      h: bh * h,
      rectRadius: 0.03,
      fill: { color: fill, transparency: 32 },
      line: { color: fill, transparency: 100 },
    });
  });

  const roads = [
    [0.03, 0.33, 0.97, 0.33], [0.02, 0.65, 0.98, 0.65],
    [0.22, 0.02, 0.22, 0.98], [0.57, 0.02, 0.57, 0.98], [0.82, 0.02, 0.82, 0.98],
    [0.02, 0.86, 0.46, 0.02], [0.4, 0.98, 0.95, 0.09],
  ];
  roads.forEach(([x1, y1, x2, y2]) => {
    addLineSegment(slide, x + x1 * w, y + y1 * h, x + x2 * w, y + y2 * h, "BCC7C9", 1.1, 18);
  });

  const route = [
    [0.11, 0.78], [0.2, 0.62], [0.36, 0.66], [0.45, 0.49], [0.59, 0.47],
    [0.68, 0.3], [0.84, 0.37], [0.76, 0.61], [0.57, 0.72], [0.36, 0.66], [0.11, 0.78],
  ];
  route.slice(0, -1).forEach((point, index) => {
    const next = route[index + 1];
    addLineSegment(
      slide,
      x + point[0] * w,
      y + point[1] * h,
      x + next[0] * w,
      y + next[1] * h,
      C.cyan,
      opts.routeWidth || 3.4,
    );
  });

  const stops = [1, 3, 5, 6, 7, 8];
  stops.forEach((routeIndex, stopIndex) => {
    const [px, py] = route[routeIndex];
    const size = opts.markerSize || 0.28;
    slide.addShape(pptx.ShapeType.ellipse, {
      x: x + px * w - size / 2,
      y: y + py * h - size / 2,
      w: size,
      h: size,
      fill: { color: C.red },
      line: { color: C.paper, width: 1.3 },
    });
    if (opts.numberStops) {
      addText(slide, String(stopIndex + 1), x + px * w - size / 2, y + py * h - size / 2, size, size, {
        fontSize: 8.5, bold: true, color: C.paper, align: "center",
      });
    }
  });

  const depotSize = opts.depotSize || 0.34;
  slide.addShape(pptx.ShapeType.ellipse, {
    x: x + route[0][0] * w - depotSize / 2,
    y: y + route[0][1] * h - depotSize / 2,
    w: depotSize,
    h: depotSize,
    fill: { color: C.green },
    line: { color: C.paper, width: 1.5 },
  });
  addText(slide, "D", x + route[0][0] * w - depotSize / 2, y + route[0][1] * h - depotSize / 2, depotSize, depotSize, {
    fontSize: 9, bold: true, color: C.paper, align: "center",
  });

  addPill(slide, opts.label || "KEYLESS ROUTE SCHEMATIC", x + 0.18, y + 0.16, opts.labelWidth || 2.15, C.paper, C.darkBlue);
  addText(slide, "No live map tiles", x + w - 1.42, y + h - 0.34, 1.18, 0.2, {
    fontSize: 8.5, bold: true, color: C.muted, align: "right",
  });
}

function addBulletList(slide, items, x, y, w, h, opts = {}) {
  const runs = [];
  items.forEach((item, index) => {
    runs.push({
      text: item,
      options: {
        bullet: { indent: 16 },
        hanging: 4,
        breakLine: index !== items.length - 1,
        paraSpaceAfterPt: opts.paraSpaceAfterPt || 10,
      },
    });
  });
  slide.addText(runs, {
    x, y, w, h,
    fontFace: "Calibri",
    fontSize: opts.fontSize || 15,
    color: opts.color || C.text,
    margin: 0,
    valign: "top",
    breakLine: false,
    fit: "shrink",
  });
}

function addDecisionBadge(slide, label, x, y, w, fill, color) {
  slide.addShape(pptx.ShapeType.roundRect, {
    x, y, w, h: 0.55,
    rectRadius: 0.08,
    fill: { color: fill },
    line: { color, width: 1.5 },
  });
  addText(slide, label, x + 0.12, y + 0.06, w - 0.24, 0.42, {
    fontSize: 12.5, bold: true, color, align: "center",
  });
}

// Slide 1 — cover
{
  const slide = pptx.addSlide();
  slide.background = { color: C.graphite };
  slide.addShape(pptx.ShapeType.arc, {
    x: -0.8, y: 5.1, w: 5.4, h: 3.2,
    adjustPoint: 0.32,
    rotate: 345,
    fill: { color: C.graphite, transparency: 100 },
    line: { color: C.cyan, width: 4, transparency: 15 },
  });
  slide.addShape(pptx.ShapeType.ellipse, {
    x: 0.76, y: 5.48, w: 0.34, h: 0.34,
    fill: { color: C.green }, line: { color: C.paper, width: 1.5 },
  });
  addText(slide, "BINSIGHT ROUTING", 0.72, 0.62, 5.1, 0.34, {
    fontSize: 12, bold: true, color: C.cyan, charSpacing: 2,
  });
  addText(slide, "From snapshot\nto dispatch", 0.72, 1.15, 6.1, 1.65, {
    fontSize: 43, bold: true, color: C.paper, valign: "top", breakLine: true,
  });
  addText(slide, "What the routing engine decides after the data is already available", 0.75, 3.02, 5.35, 0.8, {
    fontSize: 20, color: "C8D7DD", valign: "top",
  });
  addPill(slide, "VALIDATE", 0.75, 4.15, 1.25, C.paleBlue, C.darkBlue);
  addPill(slide, "PREDICT", 2.13, 4.15, 1.25, C.softTeal, C.teal);
  addPill(slide, "VALUE", 3.51, 4.15, 1.12, C.softAmber, "8A5C00");
  addPill(slide, "ROUTE", 4.76, 4.15, 1.15, C.softGreen, C.green);
  slide.addShape(pptx.ShapeType.roundRect, {
    x: 7.18, y: 0.65, w: 5.45, h: 5.95,
    rectRadius: 0.12,
    fill: { color: C.graphite2 },
    line: { color: "3A464C", width: 1.2 },
    shadow: shadow(0.28, 3, 1.5, 315),
  });
  addRouteSchematic(slide, 7.42, 0.89, 4.97, 4.53, {
    routeWidth: 3.2,
    markerSize: 0.25,
    depotSize: 0.32,
    label: "ROUTE DECISION VIEW",
    labelWidth: 1.9,
  });
  addText(slide, "The output is a capacity-feasible route proposal — not an automatic truck command.", 7.55, 5.62, 4.7, 0.65, {
    fontSize: 14.5, color: "D8E4E9", bold: true, align: "center",
  });
  addFooter(slide, true);
  slide.addNotes("Open with the scope correction: this deck does not explain how sensors collect or transmit data. It begins when a complete telemetry snapshot reaches the routing system. The central question is what BinSight does with that evidence before an operator sees a proposed route.");
}

// Slide 2 — scope
{
  const slide = pptx.addSlide("CONTENT");
  addTitle(slide, "Scope", "We start with an already-received snapshot", "The routing engine owns the decisions after this point — not sensor acquisition or transmission.");
  addCard(slide, 0.65, 1.95, 3.2, 4.35, { fill: C.paleBlue, line: "B9D8E8" });
  addText(slide, "GIVEN TO ROUTING", 0.95, 2.24, 2.55, 0.3, { fontSize: 12, bold: true, color: C.darkBlue, charSpacing: 1 });
  addText(slide, "A complete record\nfor every bin", 0.95, 2.68, 2.55, 0.82, { fontSize: 23, bold: true, color: C.text, valign: "top" });
  addBulletList(slide, [
    "Material: general, plastic cups or glass bottles",
    "Current fill estimate",
    "Time-to-overflow and probability",
    "Risk and confidence",
    "Observation age and quality",
  ], 0.98, 3.58, 2.48, 2.15, { fontSize: 13.2, paraSpaceAfterPt: 8 });
  addText(slide, "Missing evidence stays null — never a reassuring zero.", 0.98, 5.78, 2.47, 0.36, { fontSize: 11.5, bold: true, color: C.red });
  addArrow(slide, 3.98, 4.08, 4.78, 4.08, C.blue, 3);
  addCard(slide, 4.95, 1.95, 7.72, 4.35, { fill: C.paper });
  addText(slide, "WHAT WE DO", 5.28, 2.24, 2.1, 0.3, { fontSize: 12, bold: true, color: C.blue, charSpacing: 1 });
  const steps = [
    ["1", "Validate", "Can this evidence be trusted and compared?", C.blue],
    ["2", "Prioritize", "Which bins are urgent, uncertain, or safe to wait?", C.red],
    ["3", "Value the trip", "Does collecting now beat waiting or merging?", C.amber],
    ["4", "Optimize", "Which feasible stop order minimizes road effort?", C.teal],
    ["5", "Propose", "Give the operator an auditable draft decision.", C.green],
  ];
  steps.forEach((s, i) => {
    const yy = 2.78 + i * 0.6;
    addNumberNode(slide, s[0], 5.28, yy, s[3], 0.42);
    addText(slide, s[1], 5.88, yy - 0.01, 1.22, 0.3, { fontSize: 15, bold: true, color: C.text });
    addText(slide, s[2], 7.12, yy - 0.01, 4.92, 0.34, { fontSize: 13.5, color: C.muted });
  });
  addDecisionBadge(slide, "OUT OF SCOPE: how sensors obtain or transmit data", 5.28, 5.74, 6.75, C.concrete, C.muted);
  addFooter(slide);
  slide.addNotes("State the boundary clearly. The system receives one complete decision snapshot. From there it validates evidence, determines urgency, compares dispatching now with waiting, builds a feasible road route, and creates an operator-facing draft. Sensor acquisition is deliberately not part of this explanation.");
}

// Slide 3 — end-to-end decision pipeline
{
  const slide = pptx.addSlide("CONTENT");
  addTitle(slide, "Routing workflow", "Six decisions turn a snapshot into a route proposal", "Forecasting estimates what may happen; routing separately decides whether a trip makes operational sense.");
  const stages = [
    ["1", "VALIDATE", "Reject future, stale, conflicting or unmapped evidence", C.blue, C.paleBlue],
    ["2", "FUSE", "Build conservative fill, load and uncertainty", C.teal, C.softTeal],
    ["3", "FORECAST", "Estimate overflow probability and crossing time", C.darkBlue, "DDECF4"],
    ["4", "CLASSIFY", "Separate required, inspect, optional and wait", C.red, C.softRed],
    ["5", "VALUE + SOLVE", "Compare dispatch cost, then optimize the route", C.amber, C.softAmber],
    ["6", "PROPOSE", "Create an auditable operator-controlled draft", C.green, C.softGreen],
  ];
  stages.forEach((s, i) => {
    const row = i < 3 ? 0 : 1;
    const col = row === 0 ? i : 2 - (i % 3);
    const x = 0.68 + col * 4.23;
    const y = 1.95 + row * 2.35;
    addCard(slide, x, y, 3.75, 1.72, { fill: s[4], line: s[3], noShadow: true });
    addNumberNode(slide, s[0], x + 0.25, y + 0.25, s[3], 0.5);
    addText(slide, s[1], x + 0.93, y + 0.23, 2.45, 0.33, { fontSize: 15, bold: true, color: s[3], charSpacing: 0.7 });
    addText(slide, s[2], x + 0.27, y + 0.84, 3.18, 0.58, { fontSize: 14, color: C.text, valign: "top" });
  });
  addArrow(slide, 4.46, 2.81, 4.79, 2.81, C.darkSteel, 2);
  addArrow(slide, 8.69, 2.81, 9.02, 2.81, C.darkSteel, 2);
  addArrow(slide, 12.07, 3.67, 12.07, 4.21, C.darkSteel, 2);
  addArrow(slide, 9.10, 5.16, 8.77, 5.16, C.darkSteel, 2);
  addArrow(slide, 4.87, 5.16, 4.54, 5.16, C.darkSteel, 2);
  addText(slide, "Each new valid snapshot can trigger a new evaluation; accepted routes are never silently overwritten.", 2.4, 6.62, 8.5, 0.28, { fontSize: 12.5, bold: true, color: C.muted, align: "center" });
  addFooter(slide);
  slide.addNotes("Use this as the mental model for the rest of the deck. Forecasting and route optimization are deliberately separate. A forecast does not automatically create a trip. The policy must still prove the trip is required or worth its operating cost.");
}

// Slide 4 — validation
{
  const slide = pptx.addSlide("CONTENT");
  addTitle(slide, "Step 1 · Validate", "We refuse to turn uncertain data into a safe answer", "The validator preserves uncertainty, enforces one decision cutoff, and covers every configured bin.");
  addCard(slide, 0.68, 1.95, 3.35, 4.45, { fill: C.paper });
  addText(slide, "SNAPSHOT CHECKS", 0.98, 2.24, 2.55, 0.3, { fontSize: 12, bold: true, color: C.blue, charSpacing: 1 });
  const checks = [
    ["ID", "Explicit bin mapping"],
    ["UTC", "One shared decision time"],
    ["AGE", "Observation freshness"],
    ["Q", "Confidence and quality flags"],
    ["ALL", "One record per configured bin"],
  ];
  checks.forEach((c, i) => {
    const yy = 2.84 + i * 0.62;
    slide.addShape(pptx.ShapeType.roundRect, { x: 0.98, y: yy, w: 0.58, h: 0.38, rectRadius: 0.05, fill: { color: C.paleBlue }, line: { color: "B9D8E8" } });
    addText(slide, c[0], 0.98, yy + 0.01, 0.58, 0.34, { fontSize: 10, bold: true, color: C.darkBlue, align: "center" });
    addText(slide, c[1], 1.76, yy - 0.01, 1.88, 0.4, { fontSize: 14, color: C.text });
  });
  addArrow(slide, 4.18, 4.15, 5.05, 4.15, C.blue, 3);
  slide.addShape(pptx.ShapeType.hexagon, {
    x: 5.1, y: 2.5, w: 2.2, h: 3.25,
    fill: { color: C.graphite },
    line: { color: C.graphite },
    shadow: shadow(0.18, 2.5, 1, 45),
  });
  addText(slide, "QUALITY\nGATE", 5.45, 3.36, 1.5, 0.82, { fontSize: 23, bold: true, color: C.paper, align: "center" });
  addText(slide, "No silent repair", 5.42, 4.5, 1.55, 0.35, { fontSize: 11, color: C.cyan, bold: true, align: "center" });
  addArrow(slide, 7.42, 3.18, 8.02, 2.58, C.red, 2.5);
  addArrow(slide, 7.42, 4.13, 8.02, 4.13, C.amber, 2.5);
  addArrow(slide, 7.42, 5.08, 8.02, 5.68, C.green, 2.5);
  addCard(slide, 8.18, 2.03, 4.35, 1.25, { fill: C.softRed, line: C.red, noShadow: true });
  addText(slide, "COLLECTION-RELEVANT", 8.5, 2.25, 2.35, 0.3, { fontSize: 14, bold: true, color: C.red });
  addText(slide, "Urgent evidence survives review flags.", 8.5, 2.64, 3.45, 0.35, { fontSize: 13, color: C.text });
  addCard(slide, 8.18, 3.53, 4.35, 1.25, { fill: C.softAmber, line: C.amber, noShadow: true });
  addText(slide, "INSPECTION REQUIRED", 8.5, 3.75, 2.35, 0.3, { fontSize: 14, bold: true, color: "8A5C00" });
  addText(slide, "Missing, stale or conflicting evidence is visible.", 8.5, 4.14, 3.55, 0.35, { fontSize: 13, color: C.text });
  addCard(slide, 8.18, 5.03, 4.35, 1.25, { fill: C.softGreen, line: C.green, noShadow: true });
  addText(slide, "SAFE TO EVALUATE", 8.5, 5.25, 2.35, 0.3, { fontSize: 14, bold: true, color: C.green });
  addText(slide, "Only then can waiting be considered.", 8.5, 5.64, 3.45, 0.35, { fontSize: 13, color: C.text });
  addFooter(slide);
  slide.addNotes("Explain the safety philosophy: bad or incomplete evidence is never converted to zero fill or low risk. Validation can preserve an urgent collection signal, send uncertain data to inspection, or allow the rest of the routing logic to proceed. Every configured bin still gets an explicit record.");
}

// Slide 5 — forecasting
{
  const slide = pptx.addSlide("CONTENT");
  addTitle(slide, "Step 2 · Forecast", "We estimate when overflow becomes plausible", "The model produces a distribution: an expected path, a conservative upper path, and overflow probabilities.");
  addCard(slide, 0.67, 1.92, 7.45, 4.65, { fill: C.paper });
  slide.addChart(pptx.ChartType.line, [
    { name: "Expected fill", labels: ["Now", "24 h", "48 h", "96 h", "168 h"], values: [70, 74, 79, 88, 100] },
    { name: "Conservative upper", labels: ["Now", "24 h", "48 h", "96 h", "168 h"], values: [70, 78, 85, 98, 114] },
  ], {
    x: 0.98, y: 2.24, w: 6.82, h: 3.75,
    showTitle: true,
    title: "Projected fill (%)",
    titleFontFace: "Calibri",
    titleFontSize: 15,
    titleColor: C.text,
    showLegend: true,
    legendPos: "b",
    legendFontFace: "Calibri",
    legendFontSize: 10,
    chartColors: [C.blue, C.red],
    lineSize: 3,
    showValue: true,
    dataLabelPosition: "t",
    dataLabelColor: C.muted,
    dataLabelFormatCode: "0",
    catAxisLabelColor: C.muted,
    catAxisLabelFontFace: "Calibri",
    catAxisLabelFontSize: 10,
    valAxisLabelColor: C.muted,
    valAxisLabelFontFace: "Calibri",
    valAxisLabelFontSize: 10,
    valAxisMinVal: 0,
    valAxisMaxVal: 120,
    valAxisMajorUnit: 20,
    valGridLine: { color: "D9E0E2", size: 1 },
    catGridLine: { style: "none" },
    showCatName: false,
    showSerName: false,
    showBorder: false,
  });
  slide.addShape(pptx.ShapeType.line, { x: 1.53, y: 3.18, w: 5.9, h: 0, line: { color: C.red, width: 1.5, dash: "dash" } });
  addPill(slide, "100% OVERFLOW THRESHOLD", 5.42, 2.95, 2.05, C.softRed, C.red);
  addCard(slide, 8.45, 1.92, 4.2, 4.65, { fill: C.graphite, line: C.graphite });
  addText(slide, "WHAT SHAPES THE PATH", 8.8, 2.22, 3.25, 0.32, { fontSize: 12, bold: true, color: C.cyan, charSpacing: 1 });
  addBulletList(slide, [
    "Current fill and robust recent rates",
    "Hour, weekday and longer seasonal patterns",
    "Time since the last confirmed collection",
    "Known event type, timing, proximity and intensity",
    "Residual error, missing gaps and concept drift",
  ], 8.82, 2.78, 3.28, 2.25, { fontSize: 14, color: C.paper, paraSpaceAfterPt: 12 });
  slide.addShape(pptx.ShapeType.roundRect, { x: 8.82, y: 5.37, w: 3.18, h: 0.78, rectRadius: 0.06, fill: { color: C.graphite2 }, line: { color: "405159" } });
  addText(slide, "TTO = first conservative\nthreshold crossing", 9.02, 5.49, 2.77, 0.5, { fontSize: 14, bold: true, color: C.paper, align: "center" });
  addFooter(slide);
  slide.addNotes("The forecast is not one number. The expected line is the central estimate; the upper line is deliberately conservative. Time to overflow is the first point where that upper path reaches the operational threshold, interpolated between forecast steps. Known events affect forecasts only when they were known by the decision time.");
}

// Slide 6 — risk and confidence
{
  const slide = pptx.addSlide("CONTENT");
  addTitle(slide, "Step 3 · Interpret", "Risk says how soon; confidence says how much we trust it", "A high-risk prediction and a low-confidence reading are different problems and lead to different operator states.");
  addCard(slide, 0.68, 1.98, 5.65, 4.55, { fill: C.paper });
  addText(slide, "RISK LADDER", 0.98, 2.25, 2.3, 0.3, { fontSize: 12, bold: true, color: C.blue, charSpacing: 1 });
  const riskRows = [
    ["CRITICAL", "Emergency fill, ≥50% chance by 6 h, or TTO ≤ 6 h", C.red, C.softRed],
    ["HIGH", "≥50% chance by 48 h, or TTO ≤ 48 h", "9E5E00", C.softAmber],
    ["MEDIUM", "Elevated 2–7 day risk or uncertainty", C.teal, C.softTeal],
    ["LOW", "Unlikely to overflow within seven days", C.green, C.softGreen],
  ];
  riskRows.forEach((r, i) => {
    const yy = 2.78 + i * 0.82;
    slide.addShape(pptx.ShapeType.roundRect, { x: 0.98, y: yy, w: 1.35, h: 0.52, rectRadius: 0.06, fill: { color: r[3] }, line: { color: r[2], width: 1.2 } });
    addText(slide, r[0], 1.05, yy + 0.04, 1.2, 0.4, { fontSize: 11.5, bold: true, color: r[2], align: "center" });
    addText(slide, r[1], 2.58, yy - 0.01, 3.15, 0.55, { fontSize: 13.3, color: C.text });
  });
  addCard(slide, 6.7, 1.98, 5.95, 4.55, { fill: C.graphite, line: C.graphite });
  addText(slide, "CONFIDENCE FLAG", 7.02, 2.25, 2.8, 0.3, { fontSize: 12, bold: true, color: C.cyan, charSpacing: 1 });
  slide.addShape(pptx.ShapeType.ellipse, { x: 8.87, y: 3.05, w: 1.55, h: 1.55, fill: { color: C.green }, line: { color: C.paper, width: 2 } });
  addText(slide, "PASS", 8.87, 3.44, 1.55, 0.42, { fontSize: 21, bold: true, color: C.paper, align: "center" });
  const gates = [
    ["Sensor", 7.12, 2.94], ["Freshness", 10.73, 2.94],
    ["History", 7.12, 4.29], ["Interval width", 10.73, 4.29],
    ["Residual error", 7.55, 5.27], ["No active drift", 10.23, 5.27],
  ];
  gates.forEach((g) => {
    slide.addShape(pptx.ShapeType.roundRect, { x: g[1], y: g[2], w: 1.55, h: 0.48, rectRadius: 0.05, fill: { color: C.graphite2 }, line: { color: "4A5B62" } });
    addText(slide, g[0], g[1] + 0.06, g[2] + 0.04, 1.43, 0.38, { fontSize: 11.5, bold: true, color: C.paper, align: "center" });
    addArrow(slide, g[1] < 9 ? g[1] + 1.55 : g[1], g[2] + 0.24, g[1] < 9 ? 8.85 : 10.44, 3.82, "6E858F", 1.2);
  });
  addText(slide, "Low confidence cannot prove a bin is safe. It usually creates inspection — not automatic collection.", 7.25, 6.0, 4.85, 0.42, { fontSize: 12.5, bold: true, color: "C8D7DD", align: "center" });
  addFooter(slide);
  slide.addNotes("Risk and confidence are orthogonal. Risk combines current fill, overflow probability, and operational horizon. Confidence combines sensor quality, freshness, usable history, interval width, residual error, event quality, fallback use, and drift. Low confidence is intentionally not treated as low risk.");
}

// Slide 7 — mandatory vs optional
{
  const slide = pptx.addSlide("CONTENT");
  addTitle(slide, "Step 4 · Select", "First protect service; then consider useful optional pickups", "Mandatory stops cannot be traded away. Optional stops must clear quality, fill and value gates.");
  addCard(slide, 0.67, 1.95, 5.85, 4.75, { fill: C.softRed, line: C.red, noShadow: true });
  addText(slide, "MANDATORY SERVICE", 1.0, 2.24, 3.2, 0.35, { fontSize: 18, bold: true, color: C.red });
  addText(slide, "Collect even when the route's economic proxy is negative", 1.0, 2.66, 4.86, 0.45, { fontSize: 14, color: C.text });
  const mandatory = [
    "Upstream risk is critical",
    "Fresh, confident conservative fill ≥ 90%",
    "≥ 90% calibrated overflow chance before the next 6-hour opportunity",
    "Fallback TTO ≤ 6 hours when probability is unavailable",
  ];
  mandatory.forEach((m, i) => {
    const yy = 3.36 + i * 0.64;
    slide.addShape(pptx.ShapeType.ellipse, { x: 1.02, y: yy, w: 0.32, h: 0.32, fill: { color: C.red }, line: { color: C.red } });
    addText(slide, "!", 1.02, yy, 0.32, 0.3, { fontSize: 14, bold: true, color: C.paper, align: "center" });
    addText(slide, m, 1.55, yy - 0.03, 4.25, 0.42, { fontSize: 14, color: C.text });
  });
  addDecisionBadge(slide, "If required work cannot fit → dispatch is blocked", 1.0, 6.02, 4.9, C.paper, C.red);
  addCard(slide, 6.82, 1.95, 5.83, 4.75, { fill: C.paleBlue, line: C.blue, noShadow: true });
  addText(slide, "OPTIONAL CANDIDATES", 7.14, 2.24, 3.2, 0.35, { fontSize: 18, bold: true, color: C.darkBlue });
  addText(slide, "A forecast alone never justifies a trip", 7.14, 2.66, 4.8, 0.45, { fontSize: 14, color: C.text });
  const optional = [
    ["QUALITY", "Fresh enough to evaluate"],
    ["FILL", "Normally central fill ≥ 45%"],
    ["TIMING", "Useful before the next 72-hour batch"],
    ["SITE", "Can consolidate with justified same-site work"],
    ["VALUE", "Avoided loss exceeds added route cost"],
  ];
  optional.forEach((o, i) => {
    const yy = 3.18 + i * 0.54;
    slide.addShape(pptx.ShapeType.roundRect, { x: 7.14, y: yy, w: 1.05, h: 0.38, rectRadius: 0.05, fill: { color: C.paper }, line: { color: "B9D8E8" } });
    addText(slide, o[0], 7.18, yy + 0.02, 0.97, 0.32, { fontSize: 9.8, bold: true, color: C.darkBlue, align: "center" });
    addText(slide, o[1], 8.43, yy - 0.01, 3.5, 0.4, { fontSize: 13.4, color: C.text });
  });
  addDecisionBadge(slide, "Otherwise → DEFER · WAIT OR MERGE", 7.14, 6.02, 4.9, C.paper, C.darkBlue);
  addFooter(slide);
  slide.addNotes("This is the key waste-trip control. Mandatory stops are safety constraints. Optional bins are considered only after quality, fill, timing, site consolidation, and trip-value gates. A bin can have a forecast and still be deferred because a dedicated trip would be wasteful.");
}

// Slide 8 — trip value
{
  const slide = pptx.addSlide("CONTENT");
  addTitle(slide, "Step 5 · Value the trip", "We compare dispatching now with waiting or merging", "Optional collection proceeds only when the avoided-overflow benefit is larger than the full trip cost.");
  addCard(slide, 0.68, 1.97, 12.0, 2.05, { fill: C.graphite, line: C.graphite });
  addText(slide, "TRIP VALUE", 1.02, 2.25, 1.55, 0.34, { fontSize: 12, bold: true, color: C.cyan, charSpacing: 1 });
  addText(slide, "avoided overflow loss", 1.02, 2.82, 2.45, 0.5, { fontSize: 22, bold: true, color: C.softGreen, align: "center" });
  addText(slide, "−", 3.63, 2.82, 0.5, 0.5, { fontSize: 28, bold: true, color: C.paper, align: "center" });
  const costs = ["trip", "distance", "travel time", "service", "low fill"];
  costs.forEach((cost, i) => addPill(slide, cost.toUpperCase(), 4.25 + i * 1.48, 2.79, 1.28, i === 4 ? C.softRed : C.softAmber, i === 4 ? C.red : "805500"));
  addText(slide, "=", 11.68, 2.82, 0.35, 0.5, { fontSize: 28, bold: true, color: C.paper, align: "center" });
  addText(slide, "V", 12.05, 2.72, 0.35, 0.62, { fontSize: 30, bold: true, color: C.cyan, align: "center" });
  addCard(slide, 0.68, 4.35, 5.75, 2.2, { fill: C.softGreen, line: C.green, noShadow: true });
  slide.addShape(pptx.ShapeType.ellipse, { x: 1.05, y: 4.72, w: 0.82, h: 0.82, fill: { color: C.green }, line: { color: C.green } });
  addText(slide, "> 0", 1.05, 4.94, 0.82, 0.36, { fontSize: 18, bold: true, color: C.paper, align: "center" });
  addText(slide, "DISPATCH CANDIDATE", 2.18, 4.65, 3.5, 0.36, { fontSize: 18, bold: true, color: C.green });
  addText(slide, "The joint feasible route creates more avoided loss than operating cost.", 2.18, 5.14, 3.62, 0.75, { fontSize: 14, color: C.text, valign: "top" });
  addCard(slide, 6.83, 4.35, 5.85, 2.2, { fill: C.paleBlue, line: C.blue, noShadow: true });
  slide.addShape(pptx.ShapeType.ellipse, { x: 7.22, y: 4.72, w: 0.82, h: 0.82, fill: { color: C.blue }, line: { color: C.blue } });
  addText(slide, "≤ 0", 7.22, 4.94, 0.82, 0.36, { fontSize: 18, bold: true, color: C.paper, align: "center" });
  addText(slide, "WAIT OR MERGE", 8.37, 4.65, 3.5, 0.36, { fontSize: 18, bold: true, color: C.darkBlue });
  addText(slide, "Candidates stay deferred for a later opportunity or a better consolidated batch.", 8.37, 5.14, 3.7, 0.75, { fontSize: 14, color: C.text, valign: "top" });
  addText(slide, "Emergency/service-constraint work overrides this comparison.", 4.05, 6.72, 5.25, 0.25, { fontSize: 12.5, bold: true, color: C.red, align: "center" });
  addFooter(slide);
  slide.addNotes("The trip-value equation is expressed in metre-equivalent prototype decision units, not Malaysian Ringgit. It is a transparent comparison of avoided overflow loss with fixed-trip, road, travel-time, service, and low-fill costs. Mandatory work overrides the optional value gate.");
}

// Slide 9 — optimizer
{
  const slide = pptx.addSlide("CONTENT");
  addTitle(slide, "Step 6 · Optimize", "The solver chooses stops and road order together", "It uses cached OSRM road distance and duration — not straight-line distance.");
  addCard(slide, 0.66, 1.9, 7.42, 4.83, { fill: C.graphite, line: C.graphite });
  addRouteSchematic(slide, 0.91, 2.14, 6.92, 4.2, {
    routeWidth: 4,
    markerSize: 0.31,
    depotSize: 0.38,
    numberStops: true,
    label: "ILLUSTRATIVE ROUTE OUTPUT",
    labelWidth: 2.35,
  });
  addCard(slide, 8.43, 1.9, 4.22, 4.83, { fill: C.paper });
  addText(slide, "HARD CONSTRAINTS", 8.76, 2.2, 2.75, 0.32, { fontSize: 12, bold: true, color: C.blue, charSpacing: 1 });
  const constraints = [
    ["9,000 kg", "route mass"],
    ["22 m³", "compacted volume"],
    ["2 / day", "shared trip limit"],
    ["480 min", "route duration"],
    ["2 streams", "never mixed"],
  ];
  constraints.forEach((c, i) => {
    const yy = 2.82 + i * 0.66;
    slide.addShape(pptx.ShapeType.roundRect, { x: 8.77, y: yy, w: 1.42, h: 0.49, rectRadius: 0.05, fill: { color: i === 4 ? C.softTeal : C.paleBlue }, line: { color: i === 4 ? C.teal : "B9D8E8" } });
    addText(slide, c[0], 8.83, yy + 0.04, 1.3, 0.39, { fontSize: 14, bold: true, color: i === 4 ? C.teal : C.darkBlue, align: "center" });
    addText(slide, c[1], 10.46, yy + 0.01, 1.55, 0.44, { fontSize: 13, color: C.text });
  });
  addText(slide, "Required stops must be served. Optional stops receive skip penalties equal to their avoided-loss value.", 8.78, 6.11, 3.4, 0.48, { fontSize: 11.5, bold: true, color: C.muted, valign: "top" });
  addFooter(slide);
  slide.addNotes("The route solver makes two decisions jointly: which optional bins are worth including and the road order of selected stops. It enforces mass, compacted volume, daily trip, route-duration, depot-return, and waste-stream constraints. Required stops cannot be skipped; optional stops can be left for later when the route economics do not work. The slide uses a self-contained schematic rather than a live basemap; routing costs still come from the cached OSRM road matrix.");
}

// Slide 10 — operator lifecycle
{
  const slide = pptx.addSlide("CONTENT");
  addTitle(slide, "Operator control", "The engine proposes; the operator authorizes", "Every decision is immutable, auditable and explicitly labelled as collection, inspection or no collection.");
  const lifecycle = [
    ["1", "DRAFT", "Snapshot, source events, assumptions, selected and deferred bins", C.blue, C.paleBlue],
    ["2", "ACCEPTED", "Operator reviews the route and explicitly accepts", C.amber, C.softAmber],
    ["3", "MOCK DISPATCH", "One idempotent local record; no live truck contact", C.teal, C.softTeal],
    ["4", "COMPLETED", "Service event resets planning state for collected bins", C.green, C.softGreen],
  ];
  lifecycle.forEach((s, i) => {
    const x = 0.68 + i * 3.13;
    addCard(slide, x, 2.12, 2.72, 2.35, { fill: s[4], line: s[3], noShadow: true });
    addNumberNode(slide, s[0], x + 0.22, 2.36, s[3], 0.46);
    addText(slide, s[1], x + 0.85, 2.36, 1.52, 0.34, { fontSize: 14, bold: true, color: s[3] });
    addText(slide, s[2], x + 0.25, 3.04, 2.15, 0.88, { fontSize: 13.3, color: C.text, valign: "top", align: "left" });
    if (i < 3) addArrow(slide, x + 2.76, 3.28, x + 3.06, 3.28, C.darkSteel, 2);
  });
  addCard(slide, 0.68, 4.95, 12.0, 1.58, { fill: C.graphite, line: C.graphite });
  addText(slide, "WHEN CONDITIONS CHANGE DURING A ROUTE", 1.0, 5.2, 4.35, 0.3, { fontSize: 12, bold: true, color: C.cyan, charSpacing: 1 });
  addDecisionBadge(slide, "FREEZE CURRENT LEG", 1.0, 5.66, 2.15, C.graphite2, C.paper);
  addArrow(slide, 3.32, 5.93, 4.0, 5.93, C.cyan, 2.5);
  addDecisionBadge(slide, "APPLY RESIDUAL CAPACITY", 4.18, 5.66, 2.55, C.graphite2, C.paper);
  addArrow(slide, 6.9, 5.93, 7.58, 5.93, C.cyan, 2.5);
  addDecisionBadge(slide, "CREATE LINKED SUFFIX DRAFT", 7.76, 5.66, 3.15, C.graphite2, C.paper);
  addText(slide, "Never mutate\nthe accepted plan", 11.04, 5.66, 1.35, 0.5, { fontSize: 10.5, bold: true, color: C.softAmber, align: "center" });
  addFooter(slide);
  slide.addNotes("BinSight is decision support. A proposed plan is stored as a draft and requires operator acceptance. Mock dispatch is local and idempotent. If new evidence arrives during an active route, the current leg is frozen and a separate suffix draft is created using residual capacity; the accepted plan is never edited in place.");
}

// Slide 11 — worked example
{
  const slide = pptx.addSlide("CONTENT");
  addTitle(slide, "Worked example", "Three co-located bins enter — only two leave on the route", "Illustrative decision trace showing why a forecast does not automatically create a pickup.");
  const bins = [
    ["BIN A · GLASS BOTTLES", "92% fill", "TTO 4 h", "confident", "MANDATORY", C.red, C.softRed, "Emergency horizon"],
    ["BIN B · PLASTIC CUPS", "58% fill", "TTO 40 h", "confident", "OPTIONAL", C.blue, C.paleBlue, "Same recycling stream; positive joint value"],
    ["BIN C · GENERAL", "30% fill", "TTO 120 h", "confident", "DEFER", C.green, C.softGreen, "Separate stream; waiting is cheaper"],
  ];
  bins.forEach((b, i) => {
    const x = 0.68 + i * 4.22;
    addCard(slide, x, 1.98, 3.75, 3.0, { fill: b[6], line: b[5], noShadow: true });
    addText(slide, b[0], x + 0.28, 2.24, 1.72, 0.35, { fontSize: 14.5, bold: true, color: b[5] });
    addPill(slide, b[4], x + 2.15, 2.22, 1.2, C.paper, b[5]);
    addText(slide, b[1], x + 0.28, 2.92, 1.55, 0.4, { fontSize: 22, bold: true, color: C.text });
    addText(slide, b[2], x + 2.02, 2.92, 1.2, 0.4, { fontSize: 16, bold: true, color: C.text, align: "right" });
    addText(slide, b[3].toUpperCase(), x + 0.28, 3.5, 1.4, 0.28, { fontSize: 10.5, bold: true, color: C.muted, charSpacing: 1 });
    addText(slide, b[7], x + 0.28, 4.02, 3.05, 0.55, { fontSize: 14, color: C.text, valign: "top" });
  });
  addCard(slide, 0.68, 5.35, 12.0, 1.25, { fill: C.graphite, line: C.graphite });
  addText(slide, "DEPOT", 1.08, 5.73, 0.82, 0.34, { fontSize: 14, bold: true, color: C.paper, align: "center" });
  addArrow(slide, 2.0, 5.9, 3.15, 5.9, C.cyan, 3);
  addDecisionBadge(slide, "A · required", 3.34, 5.62, 1.55, C.softRed, C.red);
  addArrow(slide, 5.08, 5.9, 6.12, 5.9, C.cyan, 3);
  addDecisionBadge(slide, "B · useful", 6.3, 5.62, 1.55, C.paleBlue, C.darkBlue);
  addArrow(slide, 8.03, 5.9, 9.1, 5.9, C.cyan, 3);
  addText(slide, "DEPOT", 9.32, 5.73, 0.82, 0.34, { fontSize: 14, bold: true, color: C.paper, align: "center" });
  addText(slide, "C waits for a later batch", 10.42, 5.71, 1.63, 0.4, { fontSize: 12, bold: true, color: C.softGreen, align: "center" });
  addFooter(slide);
  slide.addNotes("Walk through the logic. Bin A is mandatory because its conservative time to overflow is inside the earliest collection horizon. Bin B is not mandatory, but it is at the same service site, shares the beverage-recycling stream with Bin A, and has positive joint trip value, so it joins. Bin C is general waste, has low fill and a long horizon, and remains on a separate later route. This is how the model avoids collecting everything with a prediction while preserving stream separation.");
}

// Slide 12 — evidence
{
  const slide = pptx.addSlide("CONTENT");
  addTitle(
    slide,
    "Evidence",
    "The current policy buys safety with more operating effort",
    `Material-aware synthetic comparison: ${evidence.scenarios} scenarios × ${evidence.replications} matched pairs × 2 policies = ${evidence.scenarios * evidence.replications * 2} runs.`
  );
  addCard(slide, 0.68, 1.9, 5.8, 4.75, { fill: C.paper });
  const overflowPair = metricPair("overflow_incidents");
  const tripPair = metricPair("collection_trips");
  const wastedPair = metricPair("wasted_pickups");
  slide.addChart(pptx.ChartType.bar, [
    { name: "Fixed", labels: ["Overflow incidents", "Trips", "Low-fill pickups"], values: [overflowPair[0], tripPair[0], wastedPair[0]] },
    { name: "Dynamic v2", labels: ["Overflow incidents", "Trips", "Low-fill pickups"], values: [overflowPair[1], tripPair[1], wastedPair[1]] },
  ], {
    x: 0.96, y: 2.24, w: 5.25, h: 3.72,
    showTitle: true,
    title: "Normal-demand counts (30-day mean)",
    titleFontFace: "Calibri", titleFontSize: 14, titleColor: C.text,
    showLegend: true, legendPos: "b", legendFontSize: 10,
    chartColors: [C.darkSteel, C.blue],
    showValue: true, dataLabelPosition: "outEnd", dataLabelColor: C.text, dataLabelFormatCode: "0.00",
    catAxisLabelColor: C.text, catAxisLabelFontSize: 10,
    valAxisLabelColor: C.muted, valAxisLabelFontSize: 9,
    valGridLine: { color: "D9E0E2", size: 1 }, catGridLine: { style: "none" },
    showBorder: false,
  });
  addText(slide, "Selectivity improves, but total operating effort rises.", 1.2, 6.02, 4.75, 0.36, { fontSize: 13, bold: true, color: C.red, align: "center" });
  addCard(slide, 6.82, 1.9, 5.83, 4.75, { fill: C.graphite, line: C.graphite });
  addText(slide, "NORMAL DEMAND", 7.16, 2.24, 2.35, 0.3, { fontSize: 12, bold: true, color: C.cyan, charSpacing: 1 });
  const stats = [
    [formatPair("overflow_incidents", 2), "overflow incidents", C.softGreen],
    [formatPair("overflow_spilled_kg", 1, " kg"), "spilled mass", C.softGreen],
    [formatPair("distance_km", 0, " km"), "road distance", C.softRed],
    [formatPair("fuel_l", 0, " L"), "fuel", C.softRed],
  ];
  stats.forEach((s, i) => {
    const yy = 2.83 + i * 0.76;
    addText(slide, s[0], 7.18, yy, 2.6, 0.4, { fontSize: 22, bold: true, color: s[2] });
    addText(slide, s[1], 9.98, yy + 0.03, 1.85, 0.34, { fontSize: 12.5, color: C.paper });
  });
  slide.addShape(pptx.ShapeType.roundRect, { x: 7.18, y: 5.95, w: 4.82, h: 0.42, rectRadius: 0.05, fill: { color: C.graphite2 }, line: { color: "42535B" } });
  addText(slide, "Decision: fixed fallback + dynamic shadow mode", 7.33, 5.99, 4.52, 0.32, { fontSize: 12.5, bold: true, color: C.softAmber, align: "center" });
  addFooter(slide);
  slide.addNotes("Be explicit about the trade-off. In the normal synthetic scenario, dynamic routing materially reduces overflow, spilled mass, and low-fill pickups, but increases total trips, distance, and fuel. Under sensor failure it is worse on overflow incidents and efficiency. The evidence supports shadow operation with a fixed-schedule fallback, not a cost-saving deployment claim.");
}

// Slide 13 — close
{
  const slide = pptx.addSlide();
  slide.background = { color: C.graphite };
  addText(slide, "THE ROUTING ANSWER", 0.78, 0.75, 3.2, 0.34, { fontSize: 12, bold: true, color: C.cyan, charSpacing: 2 });
  addText(slide, "Collect only when\nsafety or trip value\njustifies the route.", 0.78, 1.42, 7.0, 2.4, { fontSize: 42, bold: true, color: C.paper, valign: "top" });
  const summary = [
    ["Protect", "Mandatory overflow risk comes first", C.red],
    ["Consolidate", "Optional bins join only when useful", C.amber],
    ["Constrain", "Capacity, time and waste streams stay feasible", C.teal],
    ["Control", "The operator accepts every draft", C.green],
  ];
  summary.forEach((s, i) => {
    const x = 0.8 + i * 3.08;
    slide.addShape(pptx.ShapeType.ellipse, { x, y: 4.62, w: 0.52, h: 0.52, fill: { color: s[2] }, line: { color: s[2] } });
    addText(slide, String(i + 1), x, 4.64, 0.52, 0.45, { fontSize: 14, bold: true, color: C.paper, align: "center" });
    addText(slide, s[0], x + 0.72, 4.54, 1.95, 0.35, { fontSize: 16, bold: true, color: C.paper });
    addText(slide, s[1], x + 0.72, 4.98, 1.95, 0.68, { fontSize: 12.5, color: "BFD0D8", valign: "top" });
  });
  addDecisionBadge(slide, "Current recommendation: FIXED FALLBACK + DYNAMIC SHADOW MODE", 3.15, 6.35, 7.05, C.graphite2, C.softAmber);
  addFooter(slide, true);
  slide.addNotes("Close on the operational principle. Routing is not simply choosing the shortest path or collecting the fullest bin. It first protects mandatory service, then tests whether optional work is worth doing, solves a feasible route, and leaves the final authorization with the operator. Current evidence supports shadow mode with a fixed fallback.");
}

pptx.writeFile({ fileName: OUT }).catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
