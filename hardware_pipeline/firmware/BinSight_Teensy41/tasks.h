#pragma once
/*
 * tasks.h — the 3 prioritized RTOS tasks. Declared here, defined in
 * tasks.cpp, wired up (xTaskCreate + xQueueCreate) from the .ino's
 * setup(). Uses the FreeRTOS API via the Teensy 4.x port:
 *   Arduino Library Manager -> "FreeRTOS_TEENSY4" (tsandmann/freertos-teensy)
 *
 * Priority scheme (higher number = higher priority, preempts lower):
 *   Task 1 Sensing      -> TASK_SENSE_PRIORITY  (3, High)
 *   Task 2 Filter/Pack  -> TASK_FILTER_PRIORITY (2, Medium)
 *   Task 3 Transmission -> TASK_COMM_PRIORITY   (1, Low)
 *
 * Task 1 must never be blocked waiting on Task 2 or Task 3 — sensor
 * timing integrity is the highest-value property of the system. This is
 * why Task1 -> Task2 -> Task3 communication is strictly one-directional
 * through non-blocking-on-the-producer-side queue sends (xQueueSend with
 * a 0 timeout from Task 1; a full queue drops-oldest rather than stalling
 * the sensing loop).
 */

#include <Arduino_FreeRTOS.h>
#include <queue.h>
#include <semphr.h>
#include "types.h"

// Shared inter-task handles, defined in tasks.cpp, used by the .ino to
// create them before starting the scheduler.
extern QueueHandle_t g_rawDataQueue;     // RawReading,       Task1 -> Task2
extern QueueHandle_t g_packetQueue;      // PackagedReading,  Task2 -> Task3
extern SemaphoreHandle_t g_serialMutex;  // guards Serial.print debug output

// Task entry points (FreeRTOS task function signature).
void Task1_Sensing(void *pvParameters);
void Task2_FilterAndPackage(void *pvParameters);
void Task3_Transmit(void *pvParameters);

// Call once from setup(), before xTaskCreate — creates queues/mutex.
void Tasks_InitIPC();
