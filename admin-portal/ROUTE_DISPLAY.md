# How BinSight routes are displayed

The dashboard plots capacity-feasible routes directly on OpenStreetMap roads.

- **Solid teal:** smart-policy route.
- **Dashed dark gray:** fixed three-day route.
- **Green truck marker:** provisional depot.
- **Blue circle:** residential three-bin controller site.
- **Orange circle:** mixed/commercial three-bin controller site.
- **SJ-01 to SJ-11:** the 11 ESP32 sites; every site represents three underground bins.
- **Large red dots:** individual bins selected for collection in the displayed dispatch.
- **Small gray dots:** individual bins that can wait.

The layers button in the upper-right can hide either route or the individual-bin status layer. Hovering over a route shows the policy and representative simulation day. Hovering over a red/gray dot shows its UGB number, site, and `COLLECT NOW`/`can wait` status. Hovering over a site shows its label, ESP32 controller ID, household allocation, commercial allocation, and three-bin count.

The preview is a representative solved dispatch, not a promise that the truck will always follow that exact line. In live operation, each new sensor/forecast snapshot produces a new selected-stop set and the route is recalculated from the depot using the cached OSM-road distance matrix.

![BinSight representative route display](artifacts/route_map_preview.png)

Underlying route geometry: `artifacts/representative_routes.geojson`.

Underlying site table: `artifacts/district_bins.csv`.
