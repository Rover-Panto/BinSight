/*
 * BinSight_Teensy41.ino
 * =========================================================================
 * Edge firmware for the BinSight smart waste bin — Teensy 4.1.
 *
 * Custom preemptive RTOS-style multitasking (FreeRTOS via the Teensy 4.x
 * port) split into 3 prioritized tasks:
 *
 *   Task 1  Sensing            HIGH priority   (config.h: TASK_SENSE_PRIORITY)
 *   Task 2  Filter & Package   MEDIUM priority  (TASK_FILTER_PRIORITY)
 *   Task 3  Secure Transmit    LOW priority     (TASK_COMM_PRIORITY)
 *
 * Once vTaskStartScheduler() is called, FreeRTOS owns the CPU — the
 * Arduino loop() below is intentionally left effectively empty; all real
 * work happens inside the 3 tasks in tasks.cpp.
 *
 * Required libraries (Arduino Library Manager):
 *   - FreeRTOS_TEENSY4  (tsandmann/freertos-teensy port for Teensy 4.x)
 *   - Bounce2           (button debouncing)
 *   - ArduinoJson        (payload serialization)
 *   - Time                 (wall-clock timestamps; sync via the Teensy's RTC)
 *
 * Transport: USB-Serial bridge — see network.h. No Ethernet/WiFi hardware
 * needed; tools/serial_bridge.py on the laptop forwards readings to the
 * cloud backend over HTTP.
 * =========================================================================
 */

#include <arduino_freertos.h>
#include <TimeLib.h>

#include "config.h"
#include "types.h"
#include "sensors.h"
#include "network.h"
#include "tasks.h"

static TaskHandle_t h_task1, h_task2, h_task3;

// Reads the Teensy 4.1's onboard battery-backed RTC (set it once via the
// Arduino IDE's "TimeLib -> SetTime" example, or over Serial, before the
// competition demo) so timestamps stay correct without any network time.
static time_t getTeensyTime() { return Teensy3Clock.get(); }

void setup() {
  Serial.begin(115200);
  uint32_t waitStart = millis();
  while (!Serial && millis() - waitStart < 3000) { /* wait briefly for USB serial */ }

  Serial.println("=== BinSight Teensy 4.1 — booting ===");
  Serial.print("Firmware version: ");
  Serial.println(FIRMWARE_VERSION);
  Serial.print("Bin ID: ");
  Serial.println(BIN_ID);

  setSyncProvider(getTeensyTime);
  if (timeStatus() != timeSet) {
    Serial.println("WARNING: RTC time not set — timestamps will be inaccurate until synced.");
  }

  Sensors::begin();

  Serial.println("Initializing serial-bridge transport...");
  if (Network::begin()) {
    Serial.println("Serial-bridge transport ready — run tools/serial_bridge.py on the host.");
  } else {
    Serial.println("WARNING: transport init failed — Task 3 will retry continuously.");
  }

  Tasks_InitIPC();

  // Explicit priorities per the architecture: Sensing > Filter/Package > Transmit.
  xTaskCreate(Task1_Sensing,          "Sense",   TASK_SENSE_STACK_WORDS,  nullptr, TASK_SENSE_PRIORITY,  &h_task1);
  xTaskCreate(Task2_FilterAndPackage, "Filter",  TASK_FILTER_STACK_WORDS, nullptr, TASK_FILTER_PRIORITY, &h_task2);
  xTaskCreate(Task3_Transmit,         "Transmit",TASK_COMM_STACK_WORDS,   nullptr, TASK_COMM_PRIORITY,   &h_task3);

  Serial.println("Starting scheduler — control now passes to RTOS tasks.");
  Serial.flush();

  vTaskStartScheduler();

  // vTaskStartScheduler() never returns unless heap allocation for the
  // idle/timer task failed. If we reach here, something is badly wrong.
  Serial.println("FATAL: scheduler failed to start (heap exhausted?).");
  while (true) { delay(1000); }
}

void loop() {
  // Intentionally empty — FreeRTOS's scheduler has full control of the
  // CPU once vTaskStartScheduler() runs. This function is never reached
  // in normal operation.
}
