/*
 * CivicTwin-R — ESP32 Firmware
 * Water-Level Monitoring with HC-SR04 Ultrasonic Sensor
 *
 * This firmware reads distance from an HC-SR04 sensor, converts it to
 * water depth, evaluates local thresholds, and publishes JSON telemetry
 * over MQTT. It continues local threshold checks when MQTT is unavailable.
 *
 * Hardware:
 *   - ESP32 DevKit V1
 *   - HC-SR04 Ultrasonic Sensor
 *   - Status LED (optional)
 *
 * IMPORTANT: The HC-SR04 operates at 5V logic on the Echo pin.
 * For physical deployment, use a voltage divider (2.2kΩ + 3.3kΩ) on
 * the Echo pin to step down to 3.3V safe for ESP32 GPIO.
 * In Wokwi simulation, this is not needed.
 *
 * Pin Connections:
 *   HC-SR04 TRIG -> GPIO 5
 *   HC-SR04 ECHO -> GPIO 18 (through voltage divider for physical hardware)
 *   HC-SR04 VCC  -> 5V (VIN)
 *   HC-SR04 GND  -> GND
 *   Status LED   -> GPIO 2 (built-in LED on most DevKit boards)
 *
 * Wokwi: Open diagram.json in Wokwi to simulate. Adjust the distance
 *         sensor slider to simulate rising/falling water levels.
 *
 * Authors: Team #5 — CivicTwin-R
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <time.h>

// ══════════════════════════════════════════════════════════
// CONFIGURATION — Modify these for your environment
// ══════════════════════════════════════════════════════════

// WiFi
const char* WIFI_SSID     = "Wokwi-GUEST";
const char* WIFI_PASSWORD  = "";

// MQTT Broker
const char* MQTT_BROKER    = "test.mosquitto.org";  // Public broker for Wokwi demo
const int   MQTT_PORT      = 1883;
const char* MQTT_CLIENT_ID = "civictwin_node01";
const char* MQTT_USER      = "";
const char* MQTT_PASS      = "";

// MQTT Topics
const char* TOPIC_TELEMETRY = "civictwin/v1/zones/zone_01/telemetry";
const char* TOPIC_STATUS    = "civictwin/v1/zones/zone_01/status";
const char* TOPIC_ALERTS    = "civictwin/v1/zones/zone_01/alerts";

// Device Identity
const char* DEVICE_ID = "node_01";
const char* ZONE_ID   = "zone_01";

// Sensor Configuration
const int    TRIG_PIN            = 5;
const int    ECHO_PIN            = 18;
const int    LED_PIN             = 2;
const float  CONTAINER_HEIGHT_CM = 30.0;   // Height of channel/container
const float  SENSOR_MIN_CM       = 2.0;    // HC-SR04 minimum range
const float  SENSOR_MAX_CM       = 400.0;  // HC-SR04 maximum range
const float  SPEED_OF_SOUND      = 0.0343; // cm/µs (at ~20°C)

// Timing
const unsigned long READ_INTERVAL_MS    = 5000;  // 5 seconds
const unsigned long RECONNECT_DELAY_MS  = 5000;
const unsigned long WIFI_TIMEOUT_MS     = 10000;
const unsigned long STATUS_INTERVAL_MS  = 30000;

// Thresholds (percentage)
const float WARN_THRESHOLD_PCT = 70.0;
const float CRIT_THRESHOLD_PCT = 85.0;
const float HYSTERESIS_PCT     = 5.0;   // Prevents alert oscillation

// Median filter window
const int FILTER_READINGS = 5;

// ══════════════════════════════════════════════════════════
// GLOBAL STATE
// ══════════════════════════════════════════════════════════

WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);

unsigned long lastReadTime    = 0;
unsigned long lastStatusTime  = 0;
unsigned long sequence        = 0;
bool          mqttConnected   = false;
String        currentAlert    = "normal";
float         lastValidLevel  = -1.0;  // Last known good water level
int           failedReadings  = 0;
const int     MAX_FAILED      = 5;     // Max consecutive failures

// ══════════════════════════════════════════════════════════
// SENSOR FUNCTIONS
// ══════════════════════════════════════════════════════════

float readDistanceCm() {
    /*
     * Trigger HC-SR04 and measure echo time.
     * Returns distance in cm, or -1.0 on failure.
     */
    digitalWrite(TRIG_PIN, LOW);
    delayMicroseconds(2);
    digitalWrite(TRIG_PIN, HIGH);
    delayMicroseconds(10);
    digitalWrite(TRIG_PIN, LOW);

    // Timeout at ~4m max range (~23ms round trip)
    long duration = pulseIn(ECHO_PIN, HIGH, 25000);

    if (duration == 0) {
        return -1.0;  // Timeout — no echo received
    }

    float distance = (duration * SPEED_OF_SOUND) / 2.0;
    return distance;
}

float getMedianDistance() {
    /*
     * Take multiple readings and return the median.
     * Filters out transient noise and false readings.
     */
    float readings[FILTER_READINGS];
    int validCount = 0;

    for (int i = 0; i < FILTER_READINGS; i++) {
        float d = readDistanceCm();
        if (d > 0) {
            readings[validCount++] = d;
        }
        delay(30);  // Brief settling time between readings
    }

    if (validCount == 0) {
        return -1.0;
    }

    // Simple insertion sort for median
    for (int i = 1; i < validCount; i++) {
        float key = readings[i];
        int j = i - 1;
        while (j >= 0 && readings[j] > key) {
            readings[j + 1] = readings[j];
            j--;
        }
        readings[j + 1] = key;
    }

    return readings[validCount / 2];
}

// ══════════════════════════════════════════════════════════
// CONNECTIVITY
// ══════════════════════════════════════════════════════════

void connectWiFi() {
    if (WiFi.status() == WL_CONNECTED) return;

    Serial.printf("[WiFi] Connecting to %s...\n", WIFI_SSID);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    unsigned long start = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - start < WIFI_TIMEOUT_MS) {
        delay(250);
        Serial.print(".");
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.printf("\n[WiFi] Connected. IP: %s\n", WiFi.localIP().toString().c_str());
        configTime(0, 0, "pool.ntp.org");  // UTC
    } else {
        Serial.println("\n[WiFi] Connection failed — will retry");
    }
}

void connectMQTT() {
    if (mqttClient.connected()) {
        mqttConnected = true;
        return;
    }

    Serial.printf("[MQTT] Connecting to %s:%d...\n", MQTT_BROKER, MQTT_PORT);

    bool connected;
    if (strlen(MQTT_USER) > 0) {
        connected = mqttClient.connect(MQTT_CLIENT_ID, MQTT_USER, MQTT_PASS);
    } else {
        connected = mqttClient.connect(MQTT_CLIENT_ID);
    }

    if (connected) {
        mqttConnected = true;
        Serial.println("[MQTT] Connected");
    } else {
        mqttConnected = false;
        Serial.printf("[MQTT] Failed (state=%d) — will retry\n", mqttClient.state());
    }
}

// ══════════════════════════════════════════════════════════
// TELEMETRY
// ══════════════════════════════════════════════════════════

String getISO8601Timestamp() {
    time_t now;
    time(&now);
    struct tm timeinfo;
    gmtime_r(&now, &timeinfo);
    char buf[30];
    strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", &timeinfo);
    return String(buf);
}

void publishTelemetry(float distance, float waterLevel, float waterPct,
                      const char* sensorStatus) {
    sequence++;

    JsonDocument doc;
    doc["schema_version"] = "1.0";
    doc["device_id"]      = DEVICE_ID;
    doc["zone_id"]        = ZONE_ID;
    doc["sequence"]       = sequence;
    doc["timestamp"]      = getISO8601Timestamp();
    doc["distance_cm"]    = round(distance * 100) / 100.0;
    doc["water_level_cm"] = round(waterLevel * 100) / 100.0;
    doc["water_level_pct"]= round(waterPct * 100) / 100.0;
    doc["sensor_status"]  = sensorStatus;
    doc["source"]         = "wokwi";

    char payload[512];
    serializeJson(doc, payload, sizeof(payload));

    if (mqttConnected && mqttClient.connected()) {
        bool sent = mqttClient.publish(TOPIC_TELEMETRY, payload);
        if (sent) {
            Serial.printf("[TX] seq=%lu level=%.1fcm (%.1f%%) status=%s\n",
                          sequence, waterLevel, waterPct, sensorStatus);
        } else {
            Serial.println("[TX] Publish failed");
        }
    } else {
        Serial.printf("[OFFLINE] seq=%lu level=%.1fcm (%.1f%%) status=%s\n",
                      sequence, waterLevel, waterPct, sensorStatus);
    }
}

void publishAlert(const char* level, float waterPct) {
    JsonDocument doc;
    doc["zone_id"]    = ZONE_ID;
    doc["device_id"]  = DEVICE_ID;
    doc["alert_level"]= level;
    doc["water_pct"]  = waterPct;
    doc["threshold"]  = (strcmp(level, "critical") == 0) ? CRIT_THRESHOLD_PCT : WARN_THRESHOLD_PCT;
    doc["timestamp"]  = getISO8601Timestamp();

    char payload[256];
    serializeJson(doc, payload, sizeof(payload));

    if (mqttConnected && mqttClient.connected()) {
        mqttClient.publish(TOPIC_ALERTS, payload);
    }
    Serial.printf("[ALERT] %s — water at %.1f%%\n", level, waterPct);
}

// ══════════════════════════════════════════════════════════
// THRESHOLD LOGIC (runs locally even without MQTT)
// ══════════════════════════════════════════════════════════

void evaluateThreshold(float waterPct) {
    String newAlert = "normal";

    if (waterPct >= CRIT_THRESHOLD_PCT) {
        newAlert = "critical";
    } else if (waterPct >= WARN_THRESHOLD_PCT) {
        newAlert = "warning";
    } else if (currentAlert == "warning" && waterPct >= (WARN_THRESHOLD_PCT - HYSTERESIS_PCT)) {
        newAlert = "warning";  // Hysteresis — don't clear immediately
    } else if (currentAlert == "critical" && waterPct >= (CRIT_THRESHOLD_PCT - HYSTERESIS_PCT)) {
        newAlert = "critical";  // Hysteresis
    }

    if (newAlert != currentAlert) {
        currentAlert = newAlert;
        if (currentAlert == "critical" || currentAlert == "warning") {
            publishAlert(currentAlert.c_str(), waterPct);
            digitalWrite(LED_PIN, HIGH);  // LED on for alert
        } else {
            publishAlert("normal", waterPct);
            digitalWrite(LED_PIN, LOW);   // LED off
        }
    }
}

// ══════════════════════════════════════════════════════════
// MAIN
// ══════════════════════════════════════════════════════════

void setup() {
    Serial.begin(115200);
    Serial.println("\n╔══════════════════════════════════╗");
    Serial.println("║  CivicTwin-R — Node 01           ║");
    Serial.println("║  Water Level Monitor v1.0         ║");
    Serial.println("╚══════════════════════════════════╝\n");

    pinMode(TRIG_PIN, OUTPUT);
    pinMode(ECHO_PIN, INPUT);
    pinMode(LED_PIN, OUTPUT);
    digitalWrite(LED_PIN, LOW);

    connectWiFi();

    mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
    mqttClient.setBufferSize(512);
    connectMQTT();
}

void loop() {
    unsigned long now = millis();

    // Maintain connections (non-blocking)
    if (WiFi.status() != WL_CONNECTED) {
        connectWiFi();
    }
    if (!mqttClient.connected()) {
        mqttConnected = false;
        if (now - lastReadTime > RECONNECT_DELAY_MS) {
            connectMQTT();
        }
    }
    mqttClient.loop();

    // Read sensor at configured interval
    if (now - lastReadTime >= READ_INTERVAL_MS) {
        lastReadTime = now;

        float distance = getMedianDistance();

        if (distance < 0 || distance < SENSOR_MIN_CM || distance > SENSOR_MAX_CM) {
            // Invalid reading — do NOT treat as zero water level
            failedReadings++;

            if (failedReadings >= MAX_FAILED) {
                publishTelemetry(0, 0, 0, "invalid");
                Serial.printf("[SENSOR] %d consecutive failures\n", failedReadings);
            } else {
                // Use last valid level for threshold check, mark as stale
                if (lastValidLevel >= 0) {
                    float pct = (lastValidLevel / CONTAINER_HEIGHT_CM) * 100.0;
                    evaluateThreshold(pct);
                }
            }
        } else {
            failedReadings = 0;

            // Convert distance to water depth
            float waterLevel = CONTAINER_HEIGHT_CM - distance;
            if (waterLevel < 0) waterLevel = 0;
            if (waterLevel > CONTAINER_HEIGHT_CM) waterLevel = CONTAINER_HEIGHT_CM;

            float waterPct = (waterLevel / CONTAINER_HEIGHT_CM) * 100.0;
            lastValidLevel = waterLevel;

            publishTelemetry(distance, waterLevel, waterPct, "valid");
            evaluateThreshold(waterPct);
        }
    }

    // Periodic status report
    if (now - lastStatusTime >= STATUS_INTERVAL_MS) {
        lastStatusTime = now;

        JsonDocument doc;
        doc["device_id"]   = DEVICE_ID;
        doc["wifi"]        = WiFi.status() == WL_CONNECTED;
        doc["mqtt"]        = mqttConnected;
        doc["uptime_sec"]  = millis() / 1000;
        doc["sequence"]    = sequence;
        doc["alert_state"] = currentAlert;
        doc["heap_free"]   = ESP.getFreeHeap();

        char payload[256];
        serializeJson(doc, payload, sizeof(payload));

        if (mqttConnected && mqttClient.connected()) {
            mqttClient.publish(TOPIC_STATUS, payload);
        }
        Serial.printf("[STATUS] uptime=%lus seq=%lu alert=%s heap=%u\n",
                      millis() / 1000, sequence, currentAlert.c_str(), ESP.getFreeHeap());
    }
}
