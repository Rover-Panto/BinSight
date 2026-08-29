#pragma once
/*
 * esp_config.example.h — [Added 2026-08-28]
 *
 * Copy this file to esp_config.h (same folder) and fill in real values.
 * esp_config.h is gitignored and must NEVER be committed — it holds your
 * Wi-Fi password and the shared device API key.
 *
 *   cp esp_config.example.h esp_config.h
 */

// Your Wi-Fi network. The ESP32 must be able to reach whatever machine is
// running the FastAPI cloud backend over this network.
#define WIFI_SSID          "YOUR_WIFI_SSID"
#define WIFI_PASSWORD      "YOUR_WIFI_PASSWORD"

// Must match BINSIGHT_API_KEY in cloud_backend/.env EXACTLY (same value
// tools/.env's BINSIGHT_API_KEY already uses for the laptop bridge path).
#define BINSIGHT_API_KEY   "REPLACE_WITH_PROVISIONED_DEVICE_KEY"

// Base URL of the FastAPI cloud backend, no trailing slash.
//
// IMPORTANT: this can NOT be "http://localhost:8000" — the ESP32 is its
// own device with its own network stack, so "localhost" would mean the
// ESP32 itself, not your laptop. Use your laptop's actual LAN IP address
// on the same Wi-Fi network, e.g.:
//   #define CLOUD_BACKEND_URL "http://192.168.1.50:8000"
// Find your laptop's IP with `ipconfig` (Windows, look for "IPv4 Address"
// under your Wi-Fi adapter) and confirm the ESP32 can reach it by visiting
// that same URL + "/health" from another device on the same network.
#define CLOUD_BACKEND_URL  "http://192.168.1.50:8000"
