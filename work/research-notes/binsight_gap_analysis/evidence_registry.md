# BinSight gap-analysis evidence registry

**As of:** 2026-08-17  
**Scope:** Current BinSight proposal versus `Degree level question paper-SEAR 1.pdf`. GreenRoute material is explicitly excluded.

| ID | Source | Type | Evidence used | Decision supported |
|---|---|---|---|---|
| Q | `C:\Users\User\Downloads\Degree level question paper-SEAR 1.pdf` | User-provided governing brief | Deliverables, 500-household/20-commercial-unit/30-day simulation, prototype scale, power, budget, reproducibility, judging criteria, SDGs, 200-word limit | Primary compliance baseline |
| P | `C:\Users\User\OneDrive\Documents\Design Competition\outputs\BinSight_Final_Proposal.pdf` | User-provided proposal | Current 195-word body, cover, stated components and tests | Current-state evidence |
| S1 | [NEA Beverage Container Return Scheme](https://www.nea.gov.sg/our-services/waste-management/beverage-container-return-scheme) | Government, primary | Scheme covers deposit-mark plastic and metal beverage containers, 150 mL-3 L, with a 10-cent deposit | Remove glass from the claimed BCRS flow; use correct acceptance classes |
| S2 | [NEA producer briefing Q&A](https://www.nea.gov.sg/docs/default-source/default-document-library/bcrs-qna-for-19-and-26-feb-2025-producers-briefing_final.pdf) | Government, primary | Glass bottles are explicitly outside the scheme | Treat glass only as a separate team extension, if retained |
| S3 | [PJRC Teensy 4.1 specification](https://www.pjrc.com/store/teensy41.html) | Manufacturer, primary | USB serial, serial ports, Ethernet PHY with separate connector, watchdog timers, 3.3 V I/O | State the bin-to-hub interface and verify watchdog behaviour |
| S4 | [SparkFun Teensy 4.1](https://www.sparkfun.com/teensy-4-1.html) | Manufacturer/distributor, primary | Current listed unit price is USD31.50 | Three boards consume USD94.50 before sensors and structure; BOM evidence is necessary |
| S5 | [FreeRTOS scheduling](https://key.freertos.org/Documentation/02-Kernel/02-Kernel-features/01-Tasks-and-co-routines/04-Task-scheduling) | Official documentation, primary | Default fixed-priority pre-emptive scheduling and starvation risk | Replace an unqualified deterministic claim with measured timing criteria |
| S6 | [Raspberry Pi power requirements](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#typical-power-requirements) | Manufacturer, primary | Pi 4 typical active bare-board current 600 mA; camera adds about 250 mA; peripherals change demand | Select one hub, estimate power, then measure at the DC input |
| S7 | [Google OR-Tools routing](https://developers.google.com/optimization/routing) | Official documentation, primary | Supports capacity/time/resource-constrained vehicle-routing problems; large instances may be near-optimal rather than proven optimal | Define the route problem and avoid claiming mathematical optimality without solver evidence |
| S8 | [scikit-learn TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html) | Official documentation, primary | Ordinary cross-validation can train on future data and test on past data; time-ordered splitting is designed to prevent this | Use time-ordered model validation |
| S9 | [scikit-learn model evaluation](https://scikit-learn.org/stable/modules/model_evaluation.html) | Official documentation, primary | Precision, recall, F1 and regression metrics are standard evaluation tools | Define classifier and fill-prediction metrics |
| S10 | [Ultralytics custom-data training](https://docs.ultralytics.com/yolov5/tutorials/train-custom-data) | Official documentation, primary | Requires collected/labeled data, train/validation/test structure and evaluation on unseen data | State team fine-tuning, class definitions and a held-out test |
| S11 | [SimPy documentation](https://simpy.readthedocs.io/en/stable/index.html) | Official documentation, primary | Process-based discrete-event simulation for resources, vehicles and agents | Suitable implementation for the required district simulation |
| S12 | [SciPy bootstrap](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html) | Official documentation, primary | Supports paired resampling and confidence intervals | Report uncertainty for paired baseline/AI simulation runs |
| S13 | [NASA Systems Engineering Handbook appendix](https://www.nasa.gov/reference/system-engineering-handbook-appendix/) | Government, primary | Requirements flow-down, V&V planning, acceptance testing and verification matrices | Build a compact requirement-to-test matrix |
| S14 | [NIST AI RMF Core](https://airc.nist.gov/airmf-resources/airmf/5-sec-core/) | Government, primary | Calls for representative test sets, benchmarks, uncertainty, repeatable TEVV, limitations and fail-safe behaviour | Add model limits, failure handling and documented test conditions |
| S15 | [UN SDG 11](https://sdgs.un.org/goals/goal11) | Intergovernmental, primary | Target 11.6 explicitly concerns municipal waste management | Map overflow and collection KPIs to SDG 11.6 |
| S16 | [UN SDG 12](https://sdgs.un.org/goals/goal12) | Intergovernmental, primary | Target 12.5 covers waste prevention, reduction, recycling and reuse | Map return accuracy/contamination to SDG 12.5 |
| S17 | [UN SDG 13](https://sdgs.un.org/goals/goal13) | Intergovernmental, primary | Goal 13 concerns climate action; emissions claims require a documented method | Map estimated collection emissions cautiously to SDG 13 |
| S18 | [US EPA MOVES selection guidance](https://www.epa.gov/moves/moves-best-tool-my-work) | Government, primary | Simple per-mile or per-fuel GHG rates may be appropriate when a full transport model is not warranted | Use a documented factor and label CO2 as estimated, not measured |

## Source quality and exclusions

- Official, manufacturer and intergovernmental sources are used for policy, hardware, methods and SDG definitions.
- Search snippets from inaccessible academic pages were not needed for core conclusions and are not relied on here.
- ResearchGate mirrors, discussion forums, retailer blogs and unsourced marketing pages were excluded from decisive claims.
- GreenRoute documents and language were excluded at the user's direction.
