# Four-bin integration smoke evidence

This artifact set was generated from the active 44-bin configuration after
adding general, plastic, metal, and glass bins at every site and destination-
aware recycling routes.

It contains **two matched-seed, 30-day replications of the normal scenario**.
That is sufficient to exercise forecasting, planning, routing, facility unload,
chronological simulation, and the portal evidence views. It is not sufficient
for statistical inference or a production-performance claim.

Observed means in this bounded run:

| Objective metric | Fixed | Dynamic | Direction in these seeds |
|---|---:|---:|---|
| Overflow incidents | 6.0 | 4.0 | improved |
| Wasted pickups | 197.5 | 39.5 | improved |
| Distance | 766.0 km | 1,273.6 km | worsened |
| Collection trips | 18.0 | 36.0 | worsened |
| Unserved required bins | 5.5 | 0.5 | improved |

There were no routing fallbacks or unfinished trips. Because `n=2`, the wide
intervals and sign-flip values are not interpretable as evidence of a stable
effect. The dynamic policy does not yet meet the distance-reduction objective.

The large regenerated training table and fitted model are intentionally not
committed in this demonstration evidence folder. The seed manifest,
configuration hash, route/event evidence, forecast summary, and paired metrics
needed to audit and render the website are retained.
