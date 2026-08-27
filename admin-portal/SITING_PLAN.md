# BinSight Subang Jaya siting plan

## Decision

Use **33 underground bins at 11 simulated service sites**, with **three co-located 4.5 m3 bins per service group**. This is a capacity/routing topology only; it does not claim 11 deployed controllers. The separate physical profile maps one Teensy 4.1 with three fill/health channels through the shared PR #2 ESP32-C3 relay.

## Capacity calculation

Local residential generation is modeled as:

`1.90 kg/person/day x 3.7 persons/household = 7.03 kg/household/day`

For 500 households and 20 commercial units at the configurable 4.43 kg/unit/day assumption:

`500 x 7.03 + 20 x 4.43 = 3,603.6 kg/day`

Each Dutch-style bin has 4.5 m3 nominal volume. At the configurable mixed-waste density of 120 kg/m3, it holds 540 kg. A three-bin site therefore has:

`3 x 540 x 80% = 1,296 kg usable design capacity`

For a three-day collection interval and 25% reserve:

`ceil(3,603.6 x 3 x 1.25 / 1,296) = ceil(10.43) = 11 sites`

Therefore the district needs `11 x 3 = 33 bins`. The site allocation was also checked locally: every site's three-day reserved demand is below 1,296 kg.

## Preliminary site schedule

The requested coordinates below are planning anchors. The OSM/OSRM coordinate is the road-service point used in the model, not an approved excavation point.

All three bins assigned to one simulation service group share that site's coordinate. The map intentionally draws one consolidated marker and lists the three IDs in its popup; it does not spread co-located bins apart for visibility. The optimization did not add any bins, sites, or trucks beyond this service-capacity design.

| Site | Planning area | Simulation group | Bins | Households | Commercial | Daily kg | Requested latitude, longitude | OSM road point latitude, longitude | Snap m |
|---|---|---:|---:|---:|---:|---:|---|---|---:|
| SJ-01 | SS12 residential cluster | SIM-GROUP-001 | 3 | 46 | 1 | 327.81 | 3.075400, 101.575500 | 3.075280, 101.575341 | 22.1 |
| SJ-02 | SS13 residential cluster | SIM-GROUP-002 | 3 | 46 | 1 | 327.81 | 3.076500, 101.584400 | 3.076501, 101.584349 | 5.7 |
| SJ-03 | SS14 residential cluster | SIM-GROUP-003 | 3 | 46 | 1 | 327.81 | 3.071000, 101.587700 | 3.071135, 101.587700 | 14.9 |
| SJ-04 | SS15 commercial-residential cluster | SIM-GROUP-004 | 3 | 44 | 6 | 335.90 | 3.076300, 101.588800 | 3.076361, 101.588738 | 9.6 |
| SJ-05 | SS17 residential cluster | SIM-GROUP-005 | 3 | 46 | 1 | 327.81 | 3.067800, 101.578700 | 3.067696, 101.578797 | 15.8 |
| SJ-06 | SS18 residential cluster | SIM-GROUP-006 | 3 | 46 | 1 | 327.81 | 3.066200, 101.574400 | 3.066065, 101.574445 | 15.7 |
| SJ-07 | SS19 residential cluster | SIM-GROUP-007 | 3 | 46 | 1 | 327.81 | 3.082000, 101.579300 | 3.081999, 101.579284 | 1.8 |
| SJ-08 | USJ 1 mixed-use cluster | SIM-GROUP-008 | 3 | 45 | 2 | 325.21 | 3.059000, 101.588700 | 3.059093, 101.588700 | 10.3 |
| SJ-09 | USJ 2 residential cluster | SIM-GROUP-009 | 3 | 46 | 1 | 327.81 | 3.058000, 101.581500 | 3.058000, 101.581488 | 1.3 |
| SJ-10 | USJ 4 residential cluster | SIM-GROUP-010 | 3 | 46 | 1 | 327.81 | 3.046500, 101.580000 | 3.046619, 101.580001 | 13.2 |
| SJ-11 | Bandar Sunway mixed-use cluster | SIM-GROUP-011 | 3 | 43 | 4 | 320.01 | 3.073900, 101.607300 | 3.073879, 101.607300 | 2.3 |
| **Total** |  | **11 service groups** | **33** | **500** | **20** | **3,603.60** |  |  |  |

## Depot

The provisional model depot is the public OSM waste-transfer feature near Batu Tiga/Subang Jaya at **3.06192, 101.55272**. It is a routing assumption, not confirmation that the operator will allow this facility to serve the pilot.

## Why these areas

The 11 anchors spread the scenario load across the SS12-SS19 residential belt, USJ 1/2/4, and the mixed-use Bandar Sunway/SS15 areas. Commercial allocations are concentrated at SS15, USJ 1, and Bandar Sunway, while household counts are adjusted so no site violates its local three-bin design capacity.

## Mandatory field checks before installation

- Confirm ownership, MBSJ permission, collection contract, and access hours.
- Conduct utility detection and trial pits before excavation.
- Verify crane reach, lift path, stabilizer footprint, and safe truck stopping space.
- Check overhead wires, trees, signs, parked vehicles, and turning geometry.
- Check drainage, flood level, groundwater, pit waterproofing, ventilation, and gas risk.
- Preserve pedestrian clear width, universal access, sight lines, and emergency access.
- Provide wash-down, leachate control, fire access, odor control, and maintenance clearance.
- Survey actual households, businesses, waste composition, density, and seasonal peaks.

No coordinate in this document is construction-ready until those checks are signed off.
