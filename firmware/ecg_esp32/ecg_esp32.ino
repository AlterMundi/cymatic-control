/*
 * ECG ESP32 — AD8232 Heart Monitor → WiFi OSC Streaming
 *
 * Normal operation:
 *   Connects to saved WiFi and streams ECG data as OSC to the target IP.
 *
 * Configuration (two options):
 *   A. Edit the DEFAULT_* values below and re-upload (simplest)
 *   B. Send serial commands to change settings without recompiling:
 *        ssid:YourNetwork
 *        pass:YourPassword
 *        ip:192.168.1.100
 *        port:5001
 *        save           (writes to flash, restarts)
 *        status         (shows current config)
 *      Connect at 115200 baud via Arduino Serial Monitor or:
 *        python -m serial.tools.miniterm /dev/ttyUSB0 115200
 *
 * Wiring (NodeMCU ESP-32S):
 *   AD8232 OUTPUT → IO34 (GPIO 34)
 *   AD8232 LO+    → IO32 (GPIO 32)
 *   AD8232 LO-    → IO33 (GPIO 33)
 *   AD8232 3.3V   → 3V3
 *   AD8232 GND    → GND
 *
 * Usage:
 *   1. Upload to ESP32
 *   2. Configure WiFi via serial or edit defaults below
 *   3. python test_ecg_stream.py --detect   (verify stream)
 *   4. python hr_relay.py --mode ecg        (run with cymatic system)
 */

#include <WiFi.h>
#include <WiFiUdp.h>
#include <Preferences.h>

// ─── Default config (used on first boot if no saved settings) ─

#define DEFAULT_SSID       "YOUR_WIFI_SSID"
#define DEFAULT_PASS       "YOUR_WIFI_PASSWORD"
#define DEFAULT_TARGET_IP  "YOUR_PC_IP"
#define DEFAULT_TARGET_PORT 5001

// ─── Pins ────────────────────────────────────────────────────

const int PIN_ECG  = 34;
const int PIN_LO_P = 32;
const int PIN_LO_M = 33;

// ─── Sampling ────────────────────────────────────────────────

const int FS    = 250;
const int BATCH = 8;
const unsigned long SAMPLE_US = 1000000UL / FS;

// ─── Saved Configuration ─────────────────────────────────────

Preferences prefs;
String cfg_ssid, cfg_pass, cfg_ip;
int    cfg_port = DEFAULT_TARGET_PORT;

void loadConfig() {
    prefs.begin("ecg", true);
    cfg_ssid = prefs.getString("ssid", DEFAULT_SSID);
    cfg_pass = prefs.getString("pass", DEFAULT_PASS);
    cfg_ip   = prefs.getString("ip", DEFAULT_TARGET_IP);
    cfg_port = prefs.getInt("port", DEFAULT_TARGET_PORT);
    prefs.end();
}

void saveConfig() {
    prefs.begin("ecg", false);
    prefs.putString("ssid", cfg_ssid);
    prefs.putString("pass", cfg_pass);
    prefs.putString("ip", cfg_ip);
    prefs.putInt("port", cfg_port);
    prefs.end();
}

void printStatus() {
    Serial.println("\n--- Current Config ---");
    Serial.printf("  ssid: %s\n", cfg_ssid.c_str());
    Serial.printf("  pass: %s\n", cfg_pass.length() > 0 ? "****" : "(none)");
    Serial.printf("  ip:   %s\n", cfg_ip.c_str());
    Serial.printf("  port: %d\n", cfg_port);
    Serial.printf("  WiFi: %s\n", WiFi.status() == WL_CONNECTED ? "connected" : "disconnected");
    if (WiFi.status() == WL_CONNECTED)
        Serial.printf("  IP:   %s\n", WiFi.localIP().toString().c_str());
    Serial.println("---");
    Serial.println("Commands: ssid:X  pass:X  ip:X  port:X  save  status\n");
}

// ─── Serial Commands ─────────────────────────────────────────

void handleSerial() {
    if (!Serial.available()) return;
    String line = Serial.readStringUntil('\n');
    line.trim();
    if (line.length() == 0) return;

    if (line.startsWith("ssid:")) {
        cfg_ssid = line.substring(5);
        Serial.printf("SSID set to: '%s'\n", cfg_ssid.c_str());
    } else if (line.startsWith("pass:")) {
        cfg_pass = line.substring(5);
        Serial.println("Password set.");
    } else if (line.startsWith("ip:")) {
        cfg_ip = line.substring(3);
        Serial.printf("Target IP set to: %s\n", cfg_ip.c_str());
    } else if (line.startsWith("port:")) {
        cfg_port = line.substring(5).toInt();
        if (cfg_port < 1) cfg_port = DEFAULT_TARGET_PORT;
        Serial.printf("Target port set to: %d\n", cfg_port);
    } else if (line == "save") {
        saveConfig();
        Serial.println("Config saved! Restarting...");
        delay(1000);
        ESP.restart();
    } else if (line == "status") {
        printStatus();
    } else {
        Serial.printf("Unknown command: '%s'\n", line.c_str());
        Serial.println("Commands: ssid:X  pass:X  ip:X  port:X  save  status");
    }
}

// ─── Minimal OSC (raw UDP, no library needed) ────────────────

WiFiUDP udp;

int buildOsc(uint8_t* buf, const char* addr, const int* vals, int n) {
    int pos = 0;
    int alen = strlen(addr);
    memcpy(buf + pos, addr, alen); pos += alen;
    buf[pos++] = 0;
    while (pos % 4) buf[pos++] = 0;
    buf[pos++] = ',';
    for (int i = 0; i < n; i++) buf[pos++] = 'i';
    buf[pos++] = 0;
    while (pos % 4) buf[pos++] = 0;
    for (int i = 0; i < n; i++) {
        int32_t v = vals[i];
        buf[pos++] = (v >> 24) & 0xFF;
        buf[pos++] = (v >> 16) & 0xFF;
        buf[pos++] = (v >> 8)  & 0xFF;
        buf[pos++] = v & 0xFF;
    }
    return pos;
}

void sendOsc(const char* addr, const int* vals, int n) {
    uint8_t buf[128];
    int len = buildOsc(buf, addr, vals, n);
    udp.beginPacket(cfg_ip.c_str(), cfg_port);
    udp.write(buf, len);
    udp.endPacket();
}

void sendOsc1(const char* addr, int val) {
    sendOsc(addr, &val, 1);
}

// ─── ECG State ───────────────────────────────────────────────

int  ecg_buf[BATCH];
int  ecg_i = 0;
bool lo_last = false;
unsigned long lo_time = 0;
unsigned long last_sample = 0;

// ─── Setup ───────────────────────────────────────────────────

void setup() {
    Serial.begin(115200);
    delay(500);
    Serial.println("\n=== ECG ESP32 (AD8232) ===");

    pinMode(PIN_ECG, INPUT);
    pinMode(PIN_LO_P, INPUT);
    pinMode(PIN_LO_M, INPUT);
    analogReadResolution(12);
    analogSetAttenuation(ADC_11db);

    loadConfig();
    printStatus();

    if (cfg_ssid.length() == 0 || cfg_ip.length() == 0) {
        Serial.println("No config — use serial commands to configure.");
        Serial.println("  ssid:YourNetwork");
        Serial.println("  pass:YourPassword");
        Serial.println("  ip:192.168.1.100");
        Serial.println("  save");
        // Stay in serial-command loop until configured
        while (cfg_ssid.length() == 0 || cfg_ip.length() == 0) {
            handleSerial();
            delay(100);
        }
    }

    // Connect WiFi
    WiFi.mode(WIFI_STA);
    if (cfg_pass.length() > 0)
        WiFi.begin(cfg_ssid.c_str(), cfg_pass.c_str());
    else
        WiFi.begin(cfg_ssid.c_str());

    Serial.printf("Connecting to '%s'", cfg_ssid.c_str());
    for (int i = 0; i < 30 && WiFi.status() != WL_CONNECTED; i++) {
        delay(500);
        Serial.print(".");
        handleSerial();  // allow config changes during connect
    }

    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("\nWiFi FAILED. Use serial commands to reconfigure.");
        Serial.println("  ssid:NewNetwork");
        Serial.println("  pass:NewPassword");
        Serial.println("  save");
        // Keep trying, allow serial config
        while (WiFi.status() != WL_CONNECTED) {
            handleSerial();
            delay(100);
        }
    }

    Serial.printf("\nConnected! IP: %s\n", WiFi.localIP().toString().c_str());
    Serial.printf("Target: %s:%d | %d Hz\n", cfg_ip.c_str(), cfg_port, FS);
    Serial.println("Streaming ECG... (type 'status' for config)\n");

    udp.begin(0);
    last_sample = micros();
}

// ─── Loop ────────────────────────────────────────────────────

void loop() {
    // Handle serial config commands anytime
    handleSerial();

    // Reconnect if WiFi drops
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("\nWiFi lost — reconnecting...");
        WiFi.begin(cfg_ssid.c_str(), cfg_pass.c_str());
        for (int i = 0; i < 20 && WiFi.status() != WL_CONNECTED; i++) {
            delay(500);
            Serial.print(".");
            handleSerial();
        }
        if (WiFi.status() == WL_CONNECTED) {
            Serial.printf("\nReconnected! IP: %s\n", WiFi.localIP().toString().c_str());
        } else {
            Serial.println("\nStill disconnected. Use serial to reconfigure.");
            return;
        }
    }

    // ─── ECG sampling (polled at 250 Hz) ─────────────────────

    unsigned long now_us = micros();
    if (now_us - last_sample >= SAMPLE_US) {
        last_sample += SAMPLE_US;
        ecg_buf[ecg_i] = analogRead(PIN_ECG);
        ecg_i++;
        if (ecg_i >= BATCH) {
            sendOsc("/ecg/raw", ecg_buf, BATCH);
            ecg_i = 0;
        }
    }

    // Lead-off (debounced 2s, informational only)
    bool lo = (digitalRead(PIN_LO_P) == HIGH || digitalRead(PIN_LO_M) == HIGH);
    unsigned long now = millis();
    if (lo != lo_last && (now - lo_time > 2000)) {
        sendOsc1("/ecg/leads_off", lo ? 1 : 0);
        Serial.println(lo ? "! Leads off" : "+ Leads on");
        lo_last = lo;
        lo_time = now;
    }
}
