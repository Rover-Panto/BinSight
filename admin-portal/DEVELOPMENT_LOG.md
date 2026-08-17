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

14. **Startup-artifact discovery; prior result withdrawn.** The replacement holdout initially appeared to show 5.08% lower distance/fuel. Audit showed that the fixed policy swept all 33 bins at hour 6 on day zero even though every bin began empty. That one artificial 39.56 km sweep was larger than the reported total advantage. Removing it reversed the distance conclusion, so the packaged claim was withdrawn and the baseline was corrected before further reporting.

15. **Observation and leakage correction.** Hidden physical mass is now private simulation state. A separate seeded sensor model adds noise, bias, drift, outliers, missing readings, disagreement, confidence, and uncertainty. Forecast/dispatch features contain observations and history only; hidden fill is used only for labels and outcome measurement. Input validation now handles stale/future timestamps and preserves an aged last-valid reading instead of converting uncertainty to zero.

16. **Chronological operations correction.** The SimPy clock changed to minutes. OSRM durations, traffic bands, eight-minute service, depot unloading, inter-trip turnaround, and sequential trips now consume time. Waste continues to arrive during the trip, and a bin is emptied only when its service completes. The two-trip limit applies to the entire calendar day rather than independently at 06:00 and 18:00.

17. **Fuel-model correction.** Fuel is now decomposed into base driving, traffic, payload, collection idle, and depot idle components. CO2 follows total fuel. These remain configurable assumptions and are not a measured truck model.

18. **Map and replay correction.** Artificial offsets for three bins at a site were removed. All route maps now use 11 consolidated site markers with three-bin popups, attention counts, bounded Subang Jaya navigation, and accessible states. Mock tracking interpolates along saved road geometry and respects travel/service/depot timestamps.

19. **Stress evaluation added.** Base, 1.45× high-demand, 1.35× traffic, 18% missing/8% outlier sensor-failure, and 0.65× truck-capacity conditions use 30 paired replications each. Raw and equal three-day post-warm-up metrics are reported separately; scenarios are not pooled.

20. **Integer-capacity boundary correction.** During the definitive stress run, a rare load passed floating-point preselection but exceeded OR-Tools capacity after each demand was rounded upward. Preselection, exact fallback packing, proxy routing, and OR-Tools now share the same conservative integer demand rule. A regression test fixes the boundary behavior.

21. **Policy tuning lock.** Separate development seeds at base +1,010,000/+1,020,000 compared 48-, 60-, and 72-hour dispatch gaps and tighter optional/sibling rules under base and high demand. The 48-hour gap and current sibling/5 km rule retained the best safety-first fuel trade-off. Shorter emergency horizons reduced fuel but allowed materially more overflow, so the 20-hour emergency horizon was retained.

22. **Definitive validation seed.** Because earlier smoke/audit runs exposed the +910,000/+920,000 seeds, they are not called a holdout. The definitive result uses untouched arrival seeds beginning at base +1,310,000 and sensor seeds at base +1,320,000 across all five declared scenarios. Exact results are recorded in `FINAL_RESULTS.md`; any earlier 5.08% saving statement is obsolete.

These are engineering-development corrections, not confirmatory hypothesis testing. `FINAL_RESULTS.md` contains the only packaged performance result.
