# Distance-policy tuning evidence

## Decision

Do **not** change the active routing numbers from this experiment. No static
candidate lowered distance across the tested normal and high-demand conditions
without worsening another required outcome. The active `config.json` therefore
remains unchanged.

## Method

- terminating 30-day SimPy replications;
- identical arrival and sensor streams within every candidate comparison;
- development screens used arrival/sensor seed offsets +2,110,000/+2,120,000;
- the sole finalist was then evaluated on untouched offsets
  +2,310,000/+2,320,000;
- four matched replications in each of normal patterned and high-demand seasonal
  conditions; and
- production four-bin topology, vehicle limits, road matrices, and unload
  destinations were held fixed.

The tuner and complete candidate grid are in
`scripts/tune_distance_policy.py`. These runs measure model behaviour under the
configured assumptions, not field causality or real-world accuracy.

## Untouched-seed finalist

The finalist changed the sensing/replanning interval from six to three hours and
raised the conservative emergency-fill threshold from 90% to 93%.

| Scenario and metric | Current | Finalist | Modelled change |
|---|---:|---:|---:|
| Normal distance | 1,415.3 km | 1,340.3 km | 75.0 km lower (5.3%) |
| Normal trips | 40.50 | 38.75 | 1.75 fewer |
| Normal overflow incidents | 5.50 | 3.00 | 2.50 fewer |
| Normal wasted pickups | 35.00 | 29.75 | 5.25 fewer |
| High-demand distance | 1,794.3 km | 1,884.8 km | 90.4 km higher (5.0%) |
| High-demand trips | 48.75 | 52.75 | 4.00 more |
| High-demand overflow incidents | 17.50 | 14.00 | 3.50 fewer |
| High-demand overflow bin-hours | 201.25 | 202.00 | 0.75 higher |

The finalist also averaged 0.5 unfinished trips at the horizon in each scenario,
while the current policy averaged zero. Equal-weighting the two declared
conditions makes its distance slightly worse overall. It was rejected even
though several safety/selectivity metrics improved.

## Other rejected patterns

- Raising only the emergency threshold to 92–96% reduced trips and distance but
  increased overflow.
- Collecting more moderately full or co-located bins delayed urgent service and
  increased overflow.
- Longer optional gaps and higher route costs reduced some travel but produced
  worse overflow under high demand.
- Two-hour replanning reduced low-fill pickups but did not pass the overflow
  guardrail.

## Implication

The remaining distance problem is structural rather than a single bad scalar.
The next justified experiment is a demand-regime-aware policy that preserves
critical-stop priority and changes cadence/batching only when the current
evidence supports it. That requires new routing logic and a fresh seed block; it
must not be presented as a simple coefficient update.
