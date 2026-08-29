# Admin Portal Design System Reference

Last verified: 17 August 2026

This document is the implementation reference for the BinSight Streamlit operations portal in `admin-portal/`. It records the visual tokens, responsive rules, operator states, accessibility behavior, and source files that define the interface. For the task workflow, see [How to Operate the Admin Portal](HOW_TO_OPERATE_ADMIN_PORTAL.md).

## Product role

The portal is decision support for a waste-collection operator. Its primary question is: **Which bins need collection now?** It accepts one predictive snapshot for all 33 underground bins, validates the snapshot, builds capacity-feasible trips over the cached OpenStreetMap road matrix, and can record a local mock dispatch.

The portal is a prototype. It does not authenticate municipal staff, contact a vehicle, or claim measured field performance.

## Information architecture

The first page shown is **Route input**. The four top-level destinations are:

| Destination | Operator purpose | Main outputs |
| --- | --- | --- |
| Route input | Validate predictive data and decide whether collection is required | Decision state, selected bins, capacity-safe trips, OSM route preview, mock-send control |
| Operations | Inspect the configured 30-day simulation | KPI cards, fixed-versus-smart route map, forecast MAE, paired comparison table |
| Mock live tracking | Replay one representative chronological truck run | Road-leg movement, service/depot pauses, site completion states, timeline and speed controls |
| Dispatch log | Review local mock-send records | Dispatch table, latest JSON download, full payload inspection |

On desktop and tablet these destinations use a sticky tab bar. At widths of 760 px or less, the same four destinations become a fixed bottom navigation bar.

The sidebar contains the product identity, pilot configuration, experiment control, and a permanent prototype disclaimer. It is 232 px wide on desktop and follows Streamlit's automatic collapsed behavior on smaller screens.

## Design tokens

All interface colors are defined as CSS custom properties in `admin-portal/app.py`.

| Token | Value | Use |
| --- | --- | --- |
| Primary blue | `#006DAE` | Main action, active navigation, focus accent |
| Dark blue | `#00527F` | Primary hover and selected text |
| Soft blue | `#E7F2F8` | Selected navigation and neutral status |
| Graphite | `#171D20` | Sidebar, command surface, mobile navigation |
| Graphite secondary | `#242C30` | Secondary dark surfaces |
| Concrete | `#F3F5F3` | Application background |
| Paper | `#FFFFFF` | Cards and controls |
| Steel | `#D7DDDC` | Standard border |
| Dark steel | `#AAB5B4` | Strong border and secondary control edge |
| Text | `#172126` | Primary copy |
| Muted text | `#5F6B70` | Captions and supporting copy |
| Green | `#2F7D5B` | Safe state |
| Soft green | `#E7F2EC` | Safe-state background |
| Teal | `#287F83` | Supporting data color |
| Soft teal | `#E3F1F1` | Supporting data background |
| Amber | `#D99A24` | Warning and mock-only state |
| Soft amber | `#FFF3DA` | Warning background |
| Red | `#C64045` | Collection-required state |
| Soft red | `#FBE9EA` | Collection-required background |

The interface uses 4-6 px corner radii, one-pixel steel borders, and 4-6 px left status rules. Shadows are limited to the main command surface and map content so that operational states remain visually stronger than decoration.

## Typography

- Interface type: Barlow, with Segoe UI and generic sans-serif fallbacks.
- Data type: JetBrains Mono, with Consolas and generic monospace fallbacks.
- Google Fonts are imported at runtime. If the computer is offline, the local fallbacks preserve the layout.
- Primary headings use 600 weight. Labels and route data use compact monospace text where scanning exact values matters.

## Layout and responsive behavior

| Viewport | Layout behavior |
| --- | --- |
| Greater than 1024 px | 232 px dark sidebar; content constrained to 1240 px; two-column graphite command surface |
| 761-1024 px | Command surface becomes one column; its task summary moves below a divider; content padding reduces to 1.5 rem |
| 760 px or less | Dark top bar; one-column content; fixed four-item bottom navigation; extra bottom padding keeps content reachable |

The supported QA viewports are 1440x900, 768x1024, and 390x844. The browser test checks each viewport for horizontal overflow.

## Component and state reference

### Command surface

The graphite command surface states the main operator question and lists the available tasks. It is the single dominant visual surface on the page.

### Route-input states

| State | Visual treatment | Meaning |
| --- | --- | --- |
| Waiting | Soft blue with blue left rule | No snapshot has been evaluated in the current session |
| Collection required | Soft red with red left rule | At least one emergency/service-level stop is mandatory or the best optional trip has positive net value |
| Inspection required | Soft amber with amber left rule | Data quality is insufficient to safely declare no collection, without a trustworthy urgent collection trigger |
| No collection required | Soft green with green left rule | No mandatory stop exists and waiting/merging has lower expected cost |
| Mock-only warning | Soft amber with amber left rule | The next action writes a local record only |

### Route-selection states

| Map/list state | Meaning |
| --- | --- |
| Required | Critical risk, conservative fill ≥90%, or q90 overflow crossing before the next six-hour service opportunity; lower-confidence evidence below 90% remains an inspection state |
| Co-located candidate | A quality-eligible bin at a required service point considered by the joint trip-value route |
| Positive-value optional pickup | A candidate whose avoided-loss contribution makes the joint capacity/time-feasible trip better than waiting |
| Inspection required | Missing, stale, low-confidence, or disagreeing data requiring operator review |
| Defer – wait or merge | A non-mandatory bin excluded because route/service/low-fill cost exceeds current avoided-loss value |

Low-confidence mandatory readings remain in the plan but produce an operator-review warning. A required bin that cannot fit within mass, compacted-volume, route-duration or daily-trip constraints blocks the mock-send button. A draft must be accepted before mock send and cannot be sent twice.

Competition-simulation maps use one marker for each of the 11 simulated service sites. Each popup shows all three co-located bins and the marker badge shows the count requiring attention. Site shape and text reinforce color. The configured Subang Jaya bounds, zoom range 13–18, disabled wrapping, and reset control keep the operational area in view.

Mock tracking adds in-transit, servicing, completed, and depot states. Completion is timestamp-driven and appears only after service ends. Reduced-motion mode removes the pulsing animation without removing manual playback controls.

### Buttons and navigation

- Primary buttons use primary blue and dark-blue hover.
- Secondary and download buttons use paper backgrounds with dark-steel borders.
- Desktop tabs have a blue bottom indicator; mobile tabs have a blue top indicator.
- Minimum control heights are 2.9 rem for buttons, 3.15 rem for desktop tabs, and 4.6 rem for mobile navigation.

## Accessibility behavior

- Buttons and tabs show a three-pixel blue focus ring with a two-pixel offset.
- Status is communicated with text and borders as well as color.
- `prefers-reduced-motion: reduce` disables transitions, animation, and smooth scrolling.
- Mobile navigation uses large tap targets and accounts for the device safe-area inset.
- The command surface's task list has an accessible label.
- Data-heavy values use monospace text, while supporting copy uses the more readable interface face.

## Implementation map

| File | Responsibility |
| --- | --- |
| `admin-portal/app.py` | Streamlit page structure, CSS tokens, responsive rules, maps, tabs, decision states, and mock-send interface |
| `admin-portal/.streamlit/config.toml` | Streamlit theme defaults and disabled usage telemetry |
| `admin-portal/binsight/dispatch.py` | Snapshot validation, selection rules, route-plan assembly, and mock-dispatch records |
| `admin-portal/binsight/routing.py` | Capacity-constrained route solver |
| `admin-portal/binsight/network.py` | Cached OSM/OSRM service matrix and route geometry |
| `admin-portal/binsight/maps.py` | Consolidated site markers, map bounds/layers, route styling, and tracking HTML |
| `admin-portal/binsight/tracking.py` | Chronological route manifest and truck interpolation |
| `admin-portal/scripts/qa_dispatch_ui.js` | Browser workflow, screenshot, error, and overflow checks |
| `admin-portal/scripts/qa_maps_tracking.js` | Map bounds, markers, popup, tracking, responsive, and reduced-motion checks |
| `BinSight_UI_Design_Language.txt` | Repository-wide visual and interaction source language |

## Verification record

The redesign was verified on 17 August 2026 with:

- 48 Python tests passing;
- a complete demo route and local mock-dispatch browser workflow;
- exactly 11 map markers with three-bin popup rows;
- map bound/zoom/no-wrap/reset and route containment checks;
- truck movement, service-completion timing, replay reset, and reduced-motion checks;
- desktop 1440x900, tablet 768x1024, and mobile 390x844 screenshots;
- no browser console errors or page errors;
- no horizontal overflow at any tested viewport; and
- restoration of the local dispatch log after browser QA, so the test does not add a fake operator record.

## Prototype limits

- Mock dispatch writes only to `admin-portal/data/mock_truck_dispatches.jsonl`.
- No authentication, municipal role gate, API, driver application, or real vehicle connection exists.
- Snapshot validation rejects stale/future snapshots and preserves safe inspection behavior for degraded sensor data; the configured freshness window still requires field validation.
- OSRM road geometry can fall back to straight stop-to-stop preview lines. Stop order and reported distance still use the cached OSM road matrix.
- OpenStreetMap tiles and Google Fonts need network access; routing calculations can use the committed cache.
- Running the 30-day experiment is synchronous, so the sidebar control remains busy until the run finishes.
- KPI values are simulation outputs from the current configuration, not measured municipal outcomes.

## Related documentation

- [How to Operate the Admin Portal](HOW_TO_OPERATE_ADMIN_PORTAL.md)
- [Admin Routing and KPI Integration](ADMIN_INTEGRATION.md)
- [Project State](PROJECT_STATE.md)
- [Admin Portal README](../admin-portal/README.md)
