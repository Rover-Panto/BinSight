# Focus Area C research brief - Subang Jaya

## Competition fit

The supplied question paper calls for a physical prototype and reproducible 30-day digital comparison for 500 households plus 20 commercial units. Focus Area C is addressed through sensor-based fill estimation, predictive pickup prioritization, and capacity-constrained routing on Malaysian OpenStreetMap roads. The supplied proposal's Raspberry Pi/laptop hub and tree-model concept are implemented without claiming unsupported field accuracy.

## Recommended system position

Use a forecast-then-optimize decision-support architecture:

1. One ESP32 reads three ultrasonic channels and three pressure/load channels.
2. The Raspberry Pi validates the atomic three-bin payload, applies calibration, fuses volume and mass conservatively, and stores the records.
3. A tree model estimates next-48-hour fill growth and uncertainty.
4. Current and predicted risks select candidate bins.
5. OR-Tools orders capacity-feasible trips using an OSM-derived OSRM road-distance matrix.
6. A SimPy experiment compares the candidate policy against a strong every-three-days road-routed baseline.

This is decision support, not an autonomous municipal dispatch system. The revised synthetic controller uses an emergency overflow deadline, co-located-site batching, and incremental-distance gating. It passed the modeled safety comparison, but the fixed schedule remains the field safeguard until the forecast and dispatch logic are validated with real telemetry.

## Local waste basis

MBSJ's 2021 Voluntary Local Review reports **249,668.08 tonnes of solid waste in 2019** and a **1.90 kg/capita/day** generation indicator for Subang Jaya: [MBSJ Voluntary Local Review 2021](https://www.mbsj.gov.my/sites/default/files/Subang%20Jaya%20Voluntary%20Local%20Review%202021.pdf).

The Department of Statistics Malaysia's MyCensus 2020 publication gives an average household size of **3.7 persons for Subang Jaya**: [DOSM MyCensus 2020 administrative-district findings](https://www.dosm.gov.my/uploads/publications/20221018120328.pdf).

Those sources imply `1.90 x 3.7 = 7.03 kg/household/day`. For the required 500 households, that is 3,515 kg/day.

No equally current local commercial-unit disaggregation was identified. The configurable **4.43 kg/commercial unit/day** value is retained from an older Malaysian waste-minimization supporting report: [JPSPN/KPKT supporting report](https://jpspn.kpkt.gov.my/jpspn/resources/Images%20JPSPN/Sumber%20Rujukan/Kajian/Kajian%20Mengenai%20Pengurangan%20Sisa%20di%20Malaysia/SupportingReport1_V2.pdf). It contributes 88.6 kg/day, giving **3,603.6 kg/day total**. This commercial value must be replaced with an MBSJ/operator audit before field claims.

## Dutch underground-bin and truck archetype

VDL Translift lists its underground UGC container system in **3 m3 and 4.5 m3** variants; BinSight uses the 4.5 m3 option: [VDL UGC underground bin](https://www.vdltranslift.nl/en/products/crane-collection-vehicles/underground-bin-system-ugc).

VDL describes the Maxxum as suitable for 4.5 m3 underground containers and lists a **maximum lift capacity of 1,500 kg**: [VDL Maxxum](https://www.vdltranslift.nl/en/products/sideloader-collection-vehicles/sideloader-maxxum). Its IES demountable body family lists **16, 18, and 22 m3** bodies: [VDL IES](https://www.vdltranslift.nl/en/products/body-types/ies). BinSight models the 22 m3 variant, a 3.5 compaction assumption, and a conservative 9,000 kg route payload. The payload, compaction, fuel rate, legal axle loads, and Malaysian homologation must be confirmed against the selected chassis and operator.

The 120 kg/m3 loose mixed-waste density is an engineering assumption. It gives 540 kg per 4.5 m3 bin, well below the 1,500 kg crane limit but not a substitute for wet-waste testing, water-ingress allowance, or a manufacturer-approved gross container mass.

## Why 33 bins

At 80% design fill, one three-bin site provides `3 x 540 x 0.80 = 1,296 kg`. With a three-day collection interval and 25% reserve, the district needs:

`ceil(3,603.6 x 3 x 1.25 / 1,296) = 11 sites`

With three bins per controller, that is **33 underground bins and 11 ESP32 controllers**. The allocation in `SITING_PLAN.md` is balanced so each individual site also remains below its own design limit.

## OpenStreetMap implementation

The project uses OSRM table and route services over OpenStreetMap data. OSRM documents that table distances are distances along the fastest route, in metres, rather than simple straight-line measurements: [OSRM HTTP API](https://github.com/Project-OSRM/osrm-backend/blob/master/docs/http.md). The requested site anchors are snapped to accessible road-service points; all are within 22.1 m.

The road-service matrix, requested/snapped coordinates, response hash, and route geometries are cached. The dashboard attributes OpenStreetMap. Public services are suitable for prototype work, but deployment should self-host OSRM with a pinned Malaysian OSM extract and defined update policy.

The provisional depot is the public OSM waste-transfer feature at **3.06192, 101.55272** near Batu Tiga/Subang Jaya: [mapped feature context](https://mapcarta.com/W35143558). This is a routing assumption, not operator authorization. MBSJ separately publishes information about its Waste Eco Park initiative: [MBSJ Waste Eco Park](https://www.mbsj.gov.my/ms/info-projek-pengasingan-sisa-mbsj).

## Electronics and gateway readiness

Espressif's Arduino-ESP32 API supports raw ADC reads and millivolt conversion: [ESP32 ADC documentation](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/adc.html). The firmware samples the three ultrasonic sensors sequentially to limit acoustic crosstalk and takes median readings. Pressure channels are analog and require a properly rated sensor and conditioning circuit that cannot exceed 3.3 V. A hobby FSR is not acceptable for a full underground-bin mechanism.

The ESP32 publishes one three-bin JSON document by MQTT. The Raspberry Pi gateway uses the Eclipse Paho Python client interface: [Paho MQTT Python documentation](https://eclipse.dev/paho/files/paho.mqtt.python/html/index.html). Credentials are supplied through environment variables, TLS can be enabled, message IDs are deduplicated in SQLite, and collection-reset events are detected.

The fusion rule takes the larger normalized fill estimate from pressure-derived mass and ultrasonic-derived volume. That conservative rule favors overflow protection; confidence falls when the two disagree. Calibration must use known empty/full distances and several known loads for each physical channel.

## Forecast and experiment evidence

The forecasting pre-period is synthetic and separate from the 30-day policy evaluation. Its last 20% is held out chronologically. In the locked run, the tree model's 48-hour MAE was 2.527 percentage points versus 6.952 for the naive benchmark, a 63.65% modeled improvement. This validates the software against generated data only.

The policy comparison uses 30 independent paired replications. Within each pair, both policies receive identical hourly arrivals and sensor-noise arrays. Analysis is performed on replication-level paired differences, with 95% Student-t intervals and a two-sided Monte Carlo sign-flip p-value. These characterize Monte Carlo uncertainty conditional on assumptions; they do not establish real-world causal effects.

## Operational conclusion

The revised smart policy matched fixed service at zero overflow incidents, zero full-bin exposure, and zero spilled waste in a fresh 30-replication synthetic holdout. Relative to fixed collection, it reduced road distance, fuel, and modeled tailpipe CO2 by 5.08%, trips by 7.37%, stops by 14.38%, and low-fill pickups by 16.68%. Mean truck utilization increased from 59.69% to 66.91%.

The competition story should therefore emphasize:

- the defensible 33-bin/11-site sizing and OSM implementation;
- the complete ESP32-to-Raspberry-Pi data path;
- emergency deadline protection that can override normal route batching;
- co-located and nearby-bin consolidation to reduce repeated travel; and
- a fresh paired holdout that showed modeled safety parity with lower route cost.

These remain scenario results under synthetic arrivals and sensor noise. Fixed three-day service should remain the field safeguard until the seven-field AI interface, calibrated sensors, and operator constraints are validated prospectively.
