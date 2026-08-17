# Development and model-correction log

This log records material decisions made before the packaged result. Exploratory results are not final evidence.

1. **Scenario localization.** The earlier configurable Malaysian/Johor template was replaced with Subang Jaya. Residential generation changed to the MBSJ 1.90 kg/person/day indicator and DOSM 3.7-person household size. The depot moved to the provisional Batu Tiga/Subang Jaya waste-transfer feature.

2. **Dutch equipment archetype.** Bin volume changed to the VDL 4.5 m3 UGC form. The vehicle became a Maxxum/UGS-family collection archetype with a 22 m3 body, 1,500 kg lift reference, and conservative configurable 9,000 kg payload.

3. **Three-bin controller topology.** The physical design was locked to exactly three bins per microprocessor. The district generator, configuration checks, sensor schema, firmware, and gateway now enforce this invariant.

4. **Capacity sizing.** At 3,603.6 kg/day, 540 kg/bin, 80% design fill, a three-day interval, and 1.25 reserve, the district requires 10.43 three-bin sites. This was rounded up to 11 sites and 33 bins.

5. **OSM backend change.** Multiple public Overpass endpoints timed out or rate-limited during the build. The road backend was changed to OSRM services over OSM. The table response, requested/snapped coordinates, hash, and route geometries are cached. This is still OSM-road routing, but OSRM table distance is fastest-route road distance rather than a locally computed shortest-edge path.

6. **Initial 11-site allocation.** Preliminary anchors were placed across SS12-SS19, USJ 1/2/4, and Bandar Sunway. All anchors snapped to a drive service within 22.1 m.

7. **Exploratory policy study.** Small four-replication development blocks compared 48-, 60-, and 72-hour batching and route budgets. Longer gaps reduced distance but caused unacceptable overflow. A 48-hour minimum gap, 65% current / 105% upper-predicted dispatch trigger, 54% / 104% inclusion thresholds, and 30 km optional-stop budget were locked before production evaluation.

8. **Local capacity correction.** A first district-level evaluation revealed that the total 33-bin capacity was sufficient but five individual sites slightly exceeded their own reserved three-bin capacity. Those results were discarded. Household allocation was rebalanced while preserving all 11 locations, 500 households, 20 commercial units, and 3,603.6 kg/day. A new code guard now rejects any locally overloaded site.

9. **Routing timeout correction.** The first run after rebalancing stopped because OR-Tools returned no solution within the 250 ms limit for one feasible dispatch. The model now falls back to a deterministic capacity-packed nearest-neighbour route and records `routing_fallbacks`. A dedicated unit test verifies capacity and complete service. The final run used this fallback zero times.

10. **First validation isolation.** The original 30-replication result used arrival seeds beginning at base +710,000 and sensor seeds at base +720,000, separate from the +510,000/+520,000 exploratory blocks and discarded +610,000/+620,000 structurally invalid run. The failed timeout attempt did not produce or inspect policy results; it was rerun unchanged after the general solver-reliability fix.

11. **First holdout finding.** The original smart policy improved stop selectivity but worsened overflow, trips, distance, fuel, CO2, and truck utilization. That result was retained as a transparent failure finding and motivated a user-requested safety/fuel redesign rather than being presented as successful.

12. **Safety/fuel redesign.** The controller now converts the conservative 48-hour growth forecast into `time_to_overflow_hours` and `risk_level`. Critical bins can override the normal 48-hour dispatch gap. Useful sibling bins at the same three-bin site are collected without added road travel, while other optional bins are admitted only when their incremental proxy distance is within a configurable limit. No bins or sites were added.

13. **Second exploratory block.** The original +710,000/+720,000 seed block became development data for the redesign. Small paired trials selected a 20-hour emergency horizon and 5 km maximum optional incremental distance, with overflow treated as a hard acceptance constraint. Because those seeds had been inspected, they were not reused for the new packaged result.

14. **Fresh final validation.** The replacement 30-replication holdout uses previously untouched arrival seeds beginning at base +910,000 and sensor seeds at base +920,000. Both policies recorded zero overflow. The revised smart policy reduced modeled road distance/fuel/CO2 by 5.08%, trips by 7.37%, stops by 14.38%, and low-fill pickups by 16.68%. Fixed three-day service remains the field safeguard because this is synthetic validation, not measured municipal performance.

These are engineering-development corrections, not confirmatory hypothesis testing. `FINAL_RESULTS.md` contains the only packaged performance result.
