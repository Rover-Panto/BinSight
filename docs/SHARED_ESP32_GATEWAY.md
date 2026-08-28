# Shared ESP32 Gateway

Owner requirement confirmed: 28 August 2026. This is an integration contract, not a claim of implemented or hardware-tested firmware.

## Physical Scope

The demo uses one Teensy 4.1, one ESP32-C3, one Grove Vision AI V2/camera return point, and three fill-sensing bins: one general waste and two recycling. The two recycling fill channels do not imply two simultaneous vision stations.

The owner confirmed a physical laptop-hosted demo under D1. The one-Grove arrangement is the current budget baseline while D3 considers [separate versus split recycling stations](RECYCLING_STATION_OPTIONS.md). Do not add a second ESP or Grove, hardcode a material-to-bin mapping, or claim concurrent return users before that decision. PR2's three fill channels remain required under either layout.

```text
Three fill sensors -> Teensy 4.1 -- hardware UART --+
                                                  |
Camera -> Grove Vision AI V2 ------- I2C -----------+-> ONE ESP32-C3 -> Wi-Fi
                                                        |
                         main server decision ----------+-> LED/chute feedback

Fill queue        -> PR2 telemetry ingestion -> PR4 forecast -> PR1 routing/KPIs
Recognition queue -> main return-session API -> server decision -> citizen portal
```

Grove runs the classifier. Teensy schedules sensing and health checks. The ESP relays metadata and applies valid station commands; it does not train a model, calculate routes, approve refunds or decide material acceptance.

## One Firmware Target

Recommended ownership:

| Owner | Responsibility |
| --- | --- |
| PR2 | Shared C3 build/configuration, Teensy UART parser, fill queue, Wi-Fi/reconnect and common transport services |
| PR3 | Grove/SSCMA I2C adapter, raw class/confidence events, recognition queue and station-feedback module |
| Main integration | Assemble the modules into one target; implement authenticated sessions, inference API, durable decisions and citizen updates |
| PR1 | Consume fill-derived prediction snapshots and plan routes; no recognition or payout logic |
| PR4 | Own fill/overflow features, training, calibration, inference and forecast evaluation; feed PR1 through one contract after the reviewed corrections; no new gateway or dispatch service |

Agree the module interface before changing the shared entry point. Do not create separate PR2 and PR3 firmware images that each claim the same board. The network service must give both streams bounded service time; a slow HTTP request must not block sensor parsing or expiry checks.

## Wiring and Power Gates

- Use hardware UART for Teensy frames and I2C for Grove metadata. Verify exposed pins on the exact C3 Super Mini revision; do not copy a XIAO pin map.
- Check boot-strapping, USB and flash pin reservations before assigning UART, I2C and servo signals.
- Use verified 3.3V signalling and a common ground. Verify Grove pull-up voltage and the chosen module's supply requirements before connecting it.
- Power the servo and Grove from the verified supply, not from the C3's 3.3V pin. Measure brownout behaviour with inference, Wi-Fi transmission and servo movement together.
- Publish the board revision, pin table, firmware/library versions and measured current before claiming physical compatibility.

Espressif documents [two C3 UART controllers](https://docs.espressif.com/projects/esp-idf/en/stable/esp32c3/api-reference/peripherals/uart.html), [one I2C controller](https://docs.espressif.com/projects/esp-idf/en/stable/esp32c3/api-reference/peripherals/i2c.html) and [GPIO restrictions](https://docs.espressif.com/projects/esp-idf/en/stable/esp32c3/api-reference/peripherals/gpio.html). Seeed documents [SSCMA support for ESP32-C3 over I2C and UART](https://wiki.seeedstudio.com/grove_vision_ai_v2_at/). These interfaces make the shared-gateway design plausible; they do not prove this assembly or pin map works.

## Separate Event Streams

Fill events keep each bin's identity, type, acquisition time, sensor quality and calibration. They go to PR2's `/api/v1/telemetry`; the producer must complete the versioned identity/retry changes in the hardware handoff before the physical path is ready.

Recognition events contain station, session and inspection identifiers, material, confidence, object count, model version and acquisition time. They go to main's planned `/api/v1/recycling/inferences`. That HTTP endpoint is not implemented by the current policy-only server package.

One physical `device_id` may identify the gateway. Use stream-specific sequence tracking, queues and health counters. A recognition sequence must not skip because a fill event used the next number: the server requires consecutive inference results. Preserve a Teensy source/boot identity separately from the gateway boot identity. Do not regenerate event IDs on retry.

Never gate recognition or credit on a fill reading. Never send recognition into a routing adapter. Keep both stores separate from citizen browser data and retain source provenance in derived forecasts.

## Session and Recovery Rules

1. The citizen opens the station QR link; main creates a station-bound session and inspection. PR3 does not own login, QR navigation or payout.
2. The C3 relays raw Grove results. Main accepts only plastic, metal or glass at confidence >=0.70 after three consecutive matching results within the configured five-second inspection window. Main rejects other materials and owns the timeout.
3. Persist one terminal decision per inspection before applying the mock RM0.20 credit. Retries must not create another credit or servo action.
4. Execute a chute command only while its session and inspection are active, its expiry is valid and its command ID has not already executed. Reconnection must not replay an expired acceptance.
5. Queue fill events for documented replay. Expired recognition events may remain audit evidence, but cannot revive a finished inspection. Do not acknowledge durable queuing before the event is durable.
6. Report UART, Grove and network faults separately. A bounded parser/I2C timeout should contain a peripheral fault. A C3 reset or shared power loss interrupts both paths; record that common failure and resume safely.

Keep the chute in its non-accepting state after reset or loss of session authority. Test item removal/re-arm, duplicate decisions, network loss, full queues, malformed UART frames, Grove timeout and power interruption. Hardware acceptance requires concurrent fill and recognition traffic, not two separate bench demonstrations.

## References

Use the current [cross-PR review](PR_REVIEW_2026-08-28.md), [hardware handoff](CLAUDE_HARDWARE_ROUTING_HANDOFF.md), [routing handoff](CODEX_ROUTING_INTEGRATION_HANDOFF.md), [recycling contract](PR3_RECYCLING_VISION_REVIEW.md), and [budget](HARDWARE_BUDGET_LOCAL_SOURCING.md). The historical two-ESP comments are superseded by this owner requirement.
