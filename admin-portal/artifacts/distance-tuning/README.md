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

## Structural follow-up: rejected

A second bounded study used new development offsets +2,510,000/+2,520,000 and
untouched confirmation offsets +2,710,000/+2,720,000. It tested:

- optional-only route admission requiring two or three ready sites;
- 5–15 km marginal-detour limits;
- surge fallbacks based on the fleet-wide 48-hour overflow probability;
- credible time-to-overflow service windows from 12 to 48 hours;
- 500–2,000 ms route-search budgets; and
- bounded asymmetric 2-opt route ordering that retained every selected stop and
  prohibited later arrival at any mandatory stop.

Admission and 12-hour deadline variants reduced some travel only by worsening
overflow or creating later compensating trips. Deadlines of 18 hours or longer
reproduced the existing policy. Longer solver budgets and protected 2-opt found
only metre-scale same-plan improvements.

The protected 2-opt finalist then failed the untouched four-pair confirmation:

| Scenario and metric | Existing order | Protected 2-opt | Modelled change |
|---|---:|---:|---:|
| Normal distance | 1,388.8 km | 1,424.0 km | 35.2 km higher (2.5%) |
| Normal trips | 38.50 | 39.75 | 1.25 more |
| Normal overflow incidents | 2.50 | 2.75 | 0.25 more |
| Normal overflow bin-hours | 66.75 | 112.50 | 45.75 more |
| High-demand distance | 1,860.6 km | 1,869.7 km | 9.0 km higher (0.5%) |
| High-demand trips | 50.75 | 51.00 | 0.25 more |
| High-demand overflow incidents | 19.75 | 19.75 | unchanged |
| High-demand overflow bin-hours | 230.00 | 254.75 | 24.75 more |

Although each accepted reversal was locally shorter, changed completion times
altered later simulated decisions. A locally monotone route edit therefore did
not guarantee a lower 30-day system total. `route_post_optimization_enabled`
remains `false`; no rejected admission, deadline, solver-budget or route-order
candidate is active.

The next plausible distance reduction is deadhead chaining: after unloading at
the recycling facility, continue directly to the next trip instead of returning
to the depot first. That requires trusted facility-origin road matrices and an
explicit operational decision that depot return/turnaround can be skipped. It
was not assumed or implemented in this study.
