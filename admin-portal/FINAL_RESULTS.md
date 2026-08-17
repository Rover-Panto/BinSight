# BinSight Focus C - locked Subang Jaya results

## Decision summary

The capacity result is **33 underground bins at 11 sites**, with three 4.5 m3 bins and one ESP32 at each site. All sites pass both the district-wide sizing calculation and the local three-bin capacity check.

The revised operational result is promising but still cautious: the safety-constrained smart controller matched fixed collection at zero modeled overflow while reducing route distance, trips, fuel/CO2, stops, and low-fill pickups. Fixed collection every three days remains the field safeguard until real sensor and operator data validate autonomous use.

## Locked 30-day comparison

Positive beneficial effects favor the smart policy. A negative value favors fixed service. Percent change is `n/a` where the fixed mean is zero.

| KPI | Fixed mean | Smart mean | Smart effect | 95% CI for paired beneficial difference | Paired p |
|---|---:|---:|---:|---:|---:|
| Overflow incidents | 0.000 | 0.000 | no difference; n/a % | 0.000 to 0.000 incidents | 1.00000 |
| Full-bin exposure | 0.000 | 0.000 | no difference; n/a % | 0.000 to 0.000 bin-hours | 1.00000 |
| Spilled overflow waste | 0.000 | 0.000 | no difference; n/a % | 0.000 to 0.000 kg | 1.00000 |
| Road distance | 551.262 km | 523.279 km | **5.08% better** | 19.662 to 36.303 km | 0.00005 |
| Collection trips | 19.000 | 17.600 | **7.37% better** | 1.025 to 1.775 trips | 0.00005 |
| Collection stops | 330.000 | 282.533 | **14.38% better** | 44.652 to 50.281 stops | 0.00005 |
| Low-fill pickups | 33.367 | 27.800 | **16.68% better** | 2.143 to 8.990 pickups | 0.00275 |
| Fuel | 248.068 L | 235.476 L | **5.08% better** | 8.848 to 16.337 L | 0.00005 |
| Tailpipe CO2 | 664.822 kg | 631.075 kg | **5.08% better** | 23.712 to 43.782 kg | 0.00005 |
| Waste remaining at day 30 | 10,745.281 kg | 7,174.286 kg | **33.23% lower** | 2,852.112 to 4,289.879 kg | 0.00005 |
| Collected waste | 102,065.438 kg | 105,636.434 kg | **3.50% higher** | 2,852.112 to 4,289.879 kg | 0.00005 |
| Mean fill at collection | 57.276% | 69.271% | **20.94% better** | 11.407 to 12.583 percentage points | 0.00005 |
| Truck utilization | 59.687% | 66.906% | **12.09% better** | 5.700 to 8.736 percentage points | 0.00005 |
| Routing fallbacks | 0.000 | 0.000 | no difference | 0.000 to 0.000 | 1.00000 |

The revised controller achieved the safety constraint in this synthetic holdout while using fewer trips and less road travel. Its emergency override was activated when a bin's predicted overflow deadline entered the 20-hour safety horizon; optional collections were limited by their added route distance. These results support the implementation logic but do not establish real-world municipal savings.

## Forecast holdout

The separate synthetic pre-period contains 4,752 training rows and a strictly later 1,188-row holdout. For 48-hour fill growth:

- tree-model MAE: **2.527 percentage points**;
- naive benchmark MAE: **6.952 percentage points**;
- modeled MAE improvement: **63.65%**.

This shows that the implementation can learn the generated temporal process. It is not field validation; real sensor records must replace the synthetic pre-period before deployment claims.

## Sizing and siting facts

- Demand: 3,603.6 kg/day for 500 households and 20 commercial units.
- Container: 4.5 m3, modeled at 540 kg nominal mass capacity.
- Controller site: three bins, 1,620 kg nominal and 1,296 kg usable at 80% design fill.
- Design interval: three days with 1.25 reserve.
- Required sites: `ceil(10.43) = 11`; required bins: `11 x 3 = 33`.
- Site reserved loads: approximately 1,200.0 to 1,259.6 kg, all below 1,296 kg.
- Provisional depot: 3.06192, 101.55272.
- Maximum site-to-road snap: 22.1 m.

See `SITING_PLAN.md` for the 11 exact preliminary anchors and mandatory field checks.

## OSM and run provenance

- Road backend: OSRM table/route services over OpenStreetMap data.
- Cached service points: depot plus 11 sites.
- Retrieved: 2026-08-03T02:27:48.857288Z.
- Cached response SHA-256: `3718c6c6da5de35760cde23fdc15f8a582acc269969b1b289a0463439975af27`.
- Study: 30 independent paired terminating replications, 720 hours each.
- Base seed: 7,112,026.
- Production arrival seeds begin at 8,022,026; sensor seeds begin at 8,032,026.
- Policies share arrivals and sensor noise within each pair.
- No route used the deterministic timeout fallback in the final run.

## What to present to judges

The strongest defensible claim is:

> BinSight produced a fully traced sensor-to-forecast-to-OSM-route prototype and established a locally scaled 33-bin, 11-site design. In a fresh 30-replication synthetic holdout, its revised safety-constrained policy matched fixed service at zero modeled overflow while reducing road distance, fuel, and CO2 by 5.08%. Fixed service remains the field safeguard pending real telemetry and operator validation.

That is an evidence-based simulation result. Do not claim guaranteed field fuel or CO2 savings from the current thresholds.

## Next validation gate

Before autonomous routing:

1. Collect at least 8-12 weeks of calibrated three-bin telemetry and operator route logs.
2. Replace commercial generation, density, payload, fuel, dwell time, and event factors with observed distributions.
3. Retain the emergency dispatch constraint and add maximum service interval, crew hours, and disposal/unloading constraints.
4. Use rolling-origin validation and a new untouched evaluation window.
5. Require the candidate to be non-inferior on overflow before optimizing distance or stops.
6. Conduct the site surveys and approvals in `SITING_PLAN.md`.

## Reproducibility files

- `config.json`
- `data/subang_jaya_sites.json`
- `data/subang_jaya_osrm_network.json`
- `artifacts/replication_metrics.csv`
- `artifacts/policy_summary.csv`
- `artifacts/paired_effects.csv`
- `artifacts/forecast_evaluation.json`
- `artifacts/seed_manifest.json`
- `artifacts/run_provenance.json`
- `DEVELOPMENT_LOG.md`

All uncertainty statements are conditional on configured assumptions and describe Monte Carlo variability, not real-world causality or parameter uncertainty.
