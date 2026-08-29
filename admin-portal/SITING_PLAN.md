# BinSight Subang Jaya siting plan

## Decision

Use **44 underground bins at 11 simulated service sites**, with four co-located
4.5 m3 bins at every site:

1. general waste;
2. plastic recycling;
3. metal recycling; and
4. glass recycling.

This is a demonstration capacity and routing topology, not a claim that 44
physical controllers are installed. The separate physical-pilot profile still
represents the existing three-channel prototype and is intentionally marked as
incomplete for the four-bin design.

## Capacity calculation

Local generation is modelled as:

`1.90 kg/person/day x 3.7 persons/household = 7.03 kg/household/day`

For 500 households and 20 commercial units at the configurable
4.43 kg/unit/day assumption:

`500 x 7.03 + 20 x 4.43 = 3,603.6 kg/day`

For a three-day collection interval and 25% reserve, the design load is:

`3,603.6 x 3 x 1.25 = 13,513.5 kg`

The demonstration allocates that load using configurable mass fractions. Each
bin's usable capacity is its 4.5 m3 volume multiplied by material bulk density
and the 80% design-fill limit.

| Material | Mass fraction | Density kg/m3 | Usable kg/bin | District bins required by capacity | Demonstration bins |
|---|---:|---:|---:|---:|---:|
| General waste | 34% | 120 | 432 | `ceil(13,513.5 x .34 / 432) = 11` | 11 |
| Plastic | 7% | 25 | 90 | `ceil(13,513.5 x .07 / 90) = 11` | 11 |
| Metal | 10% | 70 | 252 | `ceil(13,513.5 x .10 / 252) = 6` | 11 |
| Glass | 49% | 250 | 900 | `ceil(13,513.5 x .49 / 900) = 8` | 11 |

One bin of every material is placed at every site so separation is available
consistently across the demonstration area. Metal and glass therefore have
more nominal capacity than the central composition assumption requires; field
composition and density measurements must replace these assumptions before a
real deployment.

## Preliminary site schedule

The coordinates below are planning anchors. The OSM/OSRM coordinate is the
road-service point used by the model, not an approved excavation point. The
map draws one consolidated marker per site and lists the four co-located bin
IDs in its popup.

| Site | Planning area | Simulation group | Bins | Households | Commercial | Daily kg | Requested latitude, longitude | OSM road point latitude, longitude | Snap m |
|---|---|---:|---:|---:|---:|---:|---|---|---:|
| SJ-01 | SS12 residential cluster | SIM-GROUP-001 | 4 | 46 | 1 | 327.81 | 3.075400, 101.575500 | 3.075280, 101.575341 | 22.1 |
| SJ-02 | SS13 residential cluster | SIM-GROUP-002 | 4 | 46 | 1 | 327.81 | 3.076500, 101.584400 | 3.076501, 101.584349 | 5.7 |
| SJ-03 | SS14 residential cluster | SIM-GROUP-003 | 4 | 46 | 1 | 327.81 | 3.071000, 101.587700 | 3.071135, 101.587700 | 14.9 |
| SJ-04 | SS15 commercial-residential cluster | SIM-GROUP-004 | 4 | 44 | 6 | 335.90 | 3.076300, 101.588800 | 3.076361, 101.588738 | 9.6 |
| SJ-05 | SS17 residential cluster | SIM-GROUP-005 | 4 | 46 | 1 | 327.81 | 3.067800, 101.578700 | 3.067696, 101.578797 | 15.8 |
| SJ-06 | SS18 residential cluster | SIM-GROUP-006 | 4 | 46 | 1 | 327.81 | 3.066200, 101.574400 | 3.066065, 101.574445 | 15.7 |
| SJ-07 | SS19 residential cluster | SIM-GROUP-007 | 4 | 46 | 1 | 327.81 | 3.082000, 101.579300 | 3.081999, 101.579284 | 1.8 |
| SJ-08 | USJ 1 mixed-use cluster | SIM-GROUP-008 | 4 | 45 | 2 | 325.21 | 3.059000, 101.588700 | 3.059093, 101.588700 | 10.3 |
| SJ-09 | USJ 2 residential cluster | SIM-GROUP-009 | 4 | 46 | 1 | 327.81 | 3.058000, 101.581500 | 3.058000, 101.581488 | 1.3 |
| SJ-10 | USJ 4 residential cluster | SIM-GROUP-010 | 4 | 46 | 1 | 327.81 | 3.046500, 101.580000 | 3.046619, 101.580001 | 13.2 |
| SJ-11 | Bandar Sunway mixed-use cluster | SIM-GROUP-011 | 4 | 43 | 4 | 320.01 | 3.073900, 101.607300 | 3.073879, 101.607300 | 2.3 |
| **Total** |  | **11 service groups** | **44** | **500** | **20** | **3,603.60** |  |  |  |

## Unloading destinations

- General-waste routes unload at the provisional waste depot near Batu
  Tiga/Subang Jaya at **3.06192, 101.55272**.
- Plastic, metal, and glass routes unload at the provisional **MBSJ USJ 9
  Recycling Centre** at **3.04547, 101.58697**, then return to the depot.

Both are routing assumptions. Vehicle acceptance, operating hours, contracts,
and material-specific handling must be confirmed with the facility operators.

## Why these areas

The 11 anchors spread scenario load across the SS12-SS19 residential belt, USJ
1/2/4, and the mixed-use Bandar Sunway/SS15 areas. Commercial allocations are
concentrated at SS15, USJ 1, and Bandar Sunway. Co-locating all four material
bins gives every demonstration site the same separation behaviour and makes
route comparisons reproducible.

## Mandatory field checks before installation

- Confirm ownership, MBSJ permission, collection contracts, accepted materials,
  vehicle access, and facility operating hours.
- Conduct utility detection and trial pits before excavation.
- Verify crane reach, lift path, stabilizer footprint, and safe truck stopping
  space.
- Check overhead wires, trees, signs, parked vehicles, and turning geometry.
- Check drainage, flood level, groundwater, pit waterproofing, ventilation, and
  gas risk.
- Preserve pedestrian clear width, universal access, sight lines, and emergency
  access.
- Provide wash-down, leachate control, fire access, odour control, and
  maintenance clearance.
- Survey actual households, businesses, waste composition, density, and
  seasonal peaks.

No coordinate in this document is construction-ready until those checks are
signed off.
