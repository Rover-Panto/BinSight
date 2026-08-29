# Fuel, fleet, and overflow optimization evidence

This folder is development evidence for the active four-bin, two-truck routing
policy. It is synthetic and matched-seed; it is not measured municipal fleet
performance.

## Metric and objective

`overflow_bin_hours` is aggregate overflow exposure over every bin and the
entire 30-day horizon. Each bin has its own exact event-time clock from reaching
capacity until collection finishes or the simulation ends. Two bins overflowing
for 30 minutes therefore contribute 60 bin-minutes, or 1 bin-hour. This is the
primary safety outcome. Fuel, distance, wasted pickups, unserved required bins,
and unfinished trips remain separate outcomes so the safety/fuel trade-off is
visible rather than hidden in one score.

## Selected fleet and controls

- One general-waste truck starts and unloads at the waste depot.
- One three-compartment recycling truck starts and unloads at the recycling
  facility; it can collect plastic, metal, and glass on the same trip.
- The district produces about 1,225 kg (10.2 m3 uncompacted) general waste and
  2,378 kg (22.3 m3 uncompacted) recycling per day in the configured average.
  A 22 m3 body with 3.5:1 compaction, 80% planned fill, and 1.25 reserve has
  about 49.3 m3 planned effective capacity. Average production therefore
  supports one truck per stream. A second recycling truck was screened and did
  not materially improve overflow exposure.
- Both specialized trucks may operate simultaneously. A second trip by the same
  truck is unlocked only when route capacity or arrival deadlines leave required
  bins unserved.
- Route deadlines include travel plus every earlier stop's service time. The
  truck can therefore leave before the next observation to reach two bins that
  are predicted to overflow close together.
- A directly observed plastic volume fill of 95% is a safety trigger even when
  the weight channel disagrees. Severe missing/outlier telemetry across at least
  15% of bins falls back to a two-day interval until sensing recovers.

## Development choices rejected

- Treating every low-confidence reading as required reduced overflow but caused
  about 45.5 monthly trips and 710 L fuel in the bounded screen.
- Plastic guards at 85%, 88%, and 90% dispatched too early; 97% and 98% waited
  too long and increased overflow. A 95% direct-volume guard was the best safety
  point in that screen (about 0.13 bin-hours, 638 L, and 36.5 trips).
- A three-day degraded-sensor fallback allowed excessive exposure under combined
  stress; the selected two-day fallback prevents that failure mode.
- Extra reserve vehicles were rejected because the configured production and
  selected timing policy did not justify them.

## Fresh exact-duration confirmation

`final_exact_raw.csv`, `final_exact_summary.csv`, and
`final_exact_manifest.json` contain two matched 30-day replications for each of
eleven declared scenarios. The dynamic policy reduced aggregate overflow
exposure in all eleven scenarios. Pooled equally across scenarios, exposure fell
from 577.96 to 43.74 bin-hours (92.43%), while fuel increased from 548.75 to
757.55 L and distance from 621.63 to 1,007.61 km. In the normal-patterned case,
exposure fell from 19.31 to 8.62 bin-hours (55.35%) with a 16.12% fuel premium.

Those results are a deliberate safety trade-off, not a claim that the dynamic
policy beats the fixed policy on fuel. The fixed route travels less partly by
leaving bins full for longer. Field calibration and a larger prespecified
validation set are required before operational use.
