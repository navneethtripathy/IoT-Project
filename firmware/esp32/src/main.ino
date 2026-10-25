/*
 * CivicTwin-R — ESP32 Dual-Node Cyber-Physical Firmware
 * Water-Level Monitoring with JSN-SR04T Waterproof Ultrasonic Sensor / HC-SR04
 *
 * Reads distance, calculates water depth, applies anti-chatter hysteresis,
 * controls autonomous edge warning indicator (LED/buzzer), and publishes telemetry
 * over dual MQTT topic hierarchies (zones and nodes).
 *
 * Pin Connections & Electrical Interface:
 *   Sensor TRIG -> ESP32 GPIO 5 (3.3V TTL output, 10µs trigger pulse)
 *   Sensor ECHO -> Resistor Divider -> ESP32 GPIO 18
 *       Physical JSN-SR04T / HC-SR04 outputs 5V TTL logic.
 *       CRITICAL: ESP32 GPIO is NOT 5V tolerant!
 *       Voltage Divider: ECHO -> 2.2kΩ -> GPIO 18 -> 3.3kΩ -> GND
 *       Output voltage: 5.0V * (3.3 / (2.2 + 3.3)) = 3.0V (safe 3.3V logic).
 *   Sensor VCC  -> 5.0V (VIN / USB 5V rail)
 *   Sensor GND  -> GND (Common ground)
 *   Warning LED -> GPIO 2 (Active HIGH, 220Ω current-limiting resistor)
 *   Rain Sensor -> GPIO 36 (ADC1 input, 0-4095)
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <time.h>

// ── Node Identity Selection ─────────────────────────────────────────
// Set to 1 for Node 01 (Tank 1 / Adyar / Saidapet prototype)
// Set to 2 for Node 02 (Tank 2 / Cooum / Retention prototype)
#ifndef NODE_SELECT
#define NODE_SELECT 1
#endif

#if NODE_SELECT == 1
const char* MQTT_CLIENT_ID = "civictwin_node_01";
const char* DEVICE_ID      = "node_01";
#define NODE_ID "node_01"
#define ZONE_ID "zone_01"
const float CONTAINER_HEIGHT_CM = 50.0; // Laboratory Tank 1 depth
#elif NODE_SELECT == 2
const char* MQTT_CLIENT_ID = "civictwin_node_02";
const char* DEVICE_ID      = "node_02";
#define NODE_ID "node_02"
#define ZONE_ID "zone_02"
const float CONTAINER_HEIGHT_CM = 60.0; // Laboratory Tank 2 depth
#else
const char* MQTT_CLIENT_ID = "civictwin_node_custom";
const char* DEVICE_ID      = "node_custom";
#define NODE_ID "node_custom"
#define ZONE_ID "zone_01"
const float CONTAINER_HEIGHT_CM = 30.0;
#endif

// Sensor Model Configuration:
// Set to 1 for JSN-SR04T waterproof sensor (20cm blind zone)
// Set to 0 for HC-SR04 laboratory prototype (2cm blind zone)
#ifndef USE_JSN_SR04T
#define USE_JSN_SR04T 1
#endif

#if USE_JSN_SR04T
const float SENSOR_MIN_CM = 20.0; // JSN-SR04T blind distance is ~20-25cm
const char* SENSOR_TYPE_TAG = "JSN-SR04T-WATERPROOF";
#else
const float SENSOR_MIN_CM = 2.0;  // HC-SR04 minimum distance
const char* SENSOR_TYPE_TAG = "HC-SR04";
#endif

// WiFi Configuration
const char* WIFI_SSID     = "Wokwi-GUEST";
const char* WIFI_PASSWORD = "";

// MQTT Broker Configuration
const char* MQTT_BROKER    = "localhost";
const int   MQTT_PORT      = 1883;
const char* MQTT_USER      = "";
const char* MQTT_PASS      = "";

// MQTT Topics — published to both zone and node hierarchies
const char* TOPIC_ZONE_TELEMETRY = "civictwin/v1/zones/" ZONE_ID "/telemetry";
const char* TOPIC_ZONE_STATUS    = "civictwin/v1/zones/" ZONE_ID "/status";
const char* TOPIC_ZONE_ALERTS    = "civictwin/v1/zones/" ZONE_ID "/alerts";

const char* TOPIC_NODE_TELEMETRY = "civictwin/v1/nodes/" NODE_ID "/telemetry";
const char* TOPIC_NODE_STATUS    = "civictwin/v1/nodes/" NODE_ID "/status";
const char* TOPIC_NODE_ALERTS    = "civictwin/v1/nodes/" NODE_ID "/alerts";

#ifndef DATA_SOURCE
#define DATA_SOURCE "FIELD_SENSOR"
#endif

// Sensor Geometry and Pins
const int   TRIG_PIN            = 5;
const int   ECHO_PIN            = 18;
const int   LED_PIN             = 2;
// Wokwi potentiometer stand-in for an analog rain sensor.
const int   RAIN_SENSOR_PIN      = 36;  // ESP32 VP / ADC1 input
const int   RAIN_ADC_MIN         = 0;
const int   RAIN_ADC_MAX         = 4095;
// Note: CONTAINER_HEIGHT_CM and SENSOR_MIN_CM are configured per-node above.
const float SENSOR_MAX_CM       = 400.0;
const float SPEED_OF_SOUND      = 0.0343;

// Intervals
const unsigned long READ_INTERVAL_MS   = 5000;
const unsigned long RECONNECT_DELAY_MS = 5000;
const unsigned long WIFI_TIMEOUT_MS    = 10000;
const unsigned long STATUS_INTERVAL_MS = 30000;

// Thresholds and Hysteresis
// Disclaimer: These are configurable prototype thresholds for laboratory simulation
// and are NOT officially validated flood warning thresholds for Chennai river basins.
const float WARN_THRESHOLD_PCT = 70.0;
const float CRIT_THRESHOLD_PCT = 85.0;
const float HYSTERESIS_PCT     = 3.0;
const int   FILTER_READINGS    = 5;

WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);

unsigned long lastReadTime    = 0;
unsigned long lastStatusTime  = 0;
unsigned long sequence        = 0;
bool          mqttConnected   = false;
String        currentAlert    = "normal";
float         lastValidLevel  = -1.0;
int           failedReadings  = 0;
const int     MAX_FAILED      = 5;

int readRainSensorRaw() {
    int raw = analogRead(RAIN_SENSOR_PIN);
    return constrain(raw, RAIN_ADC_MIN, RAIN_ADC_MAX);
}

float rainIndicatorPct(int raw) {
    return (static_cast<float>(raw - RAIN_ADC_MIN) /
            static_cast<float>(RAIN_ADC_MAX - RAIN_ADC_MIN)) * 100.0;
}

float readDistanceCm() {
    digitalWrite(TRIG_PIN, LOW);
    delayMicroseconds(2);
    digitalWrite(TRIG_PIN, HIGH);
    delayMicroseconds(10);
    digitalWrite(TRIG_PIN, LOW);

    long duration = pulseIn(ECHO_PIN, HIGH, 25000);
    if (duration == 0) {
        return -1.0;
    }
    return (duration * SPEED_OF_SOUND) / 2.0;
}

float getMedianDistance() {
    float readings[FILTER_READINGS];
    int validCount = 0;

    for (int i = 0; i < FILTER_READINGS; i++) {
        float d = readDistanceCm();
        if (d > 0) {
            readings[validCount++] = d;
        }
        delay(30);
    }

    if (validCount == 0) {
        return -1.0;
    }

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
        Serial.printf("\n[WiFi] Connected: %s\n", WiFi.localIP().toString().c_str());
        configTime(0, 0, "pool.ntp.org");
    } else {
        Serial.println("\n[WiFi] Connection timeout; will retry");
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
        Serial.printf("[MQTT] Connect failed (rc=%d)\n", mqttClient.state());
    }
}

String getISO8601Timestamp() {
    time_t now;
    time(&now);
    struct tm timeinfo;
    gmtime_r(&now, &timeinfo);
    char buf[30];
    strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", &timeinfo);
    return String(buf);
}

void publishTelemetry(float distance, float waterLevel, float waterPct, const char* sensorStatus) {
    sequence++;
    int rainRaw = readRainSensorRaw();
    float rainPct = rainIndicatorPct(rainRaw);

    JsonDocument doc;
    doc["schema_version"] = "1.0";
    doc["device_id"]      = DEVICE_ID;
    doc["zone_id"]        = ZONE_ID;
    doc["sequence"]       = sequence;
    doc["timestamp"]      = getISO8601Timestamp();

    if (strcmp(sensorStatus, "valid") == 0) {
        doc["distance_cm"]    = round(distance * 100) / 100.0;
        doc["water_level_cm"] = round(waterLevel * 100) / 100.0;
        doc["water_level_pct"]= round(waterPct * 100) / 100.0;
    } else {
        // Do not fabricate zero readings for sensor failures or timeouts
        doc["distance_cm"]    = nullptr;
        doc["water_level_cm"] = nullptr;
        doc["water_level_pct"]= nullptr;
    }
    doc["sensor_status"]  = sensorStatus;
    doc["source"]         = DATA_SOURCE;
    doc["rain_sensor_raw"] = rainRaw;
    doc["rain_indicator_pct"] = round(rainPct * 100) / 100.0;
    JsonArray qualityFlags = doc["quality_flags"].to<JsonArray>();
    qualityFlags.add("rain_indicator_uncalibrated");

    char payload[512];
    serializeJson(doc, payload, sizeof(payload));

    if (mqttConnected && mqttClient.connected()) {
        bool sentZone = mqttClient.publish(TOPIC_ZONE_TELEMETRY, payload);
        bool sentNode = mqttClient.publish(TOPIC_NODE_TELEMETRY, payload);
        if (sentZone || sentNode) {
            Serial.printf("[TX] seq=%lu level=%.1fcm (%.1f%%) rain=%.1f%% status=%s\n",
                          sequence, waterLevel, waterPct, rainPct, sensorStatus);
        } else {
            Serial.println("[TX] Publish failed");
        }
    } else {
        Serial.printf("[OFFLINE] seq=%lu level=%.1fcm (%.1f%%) rain=%.1f%% status=%s\n",
                      sequence, waterLevel, waterPct, rainPct, sensorStatus);
    }
}

void publishAlert(const char* level, float waterPct) {
    JsonDocument doc;
    doc["zone_id"]     = ZONE_ID;
    doc["node_id"]     = NODE_ID;
    doc["device_id"]   = DEVICE_ID;
    doc["alert_level"] = level;
    doc["water_pct"]   = waterPct;
    doc["threshold"]   = (strcmp(level, "critical") == 0) ? CRIT_THRESHOLD_PCT : WARN_THRESHOLD_PCT;
    doc["timestamp"]   = getISO8601Timestamp();

    char payload[256];
    serializeJson(doc, payload, sizeof(payload));

    if (mqttConnected && mqttClient.connected()) {
        mqttClient.publish(TOPIC_ZONE_ALERTS, payload);
        mqttClient.publish(TOPIC_NODE_ALERTS, payload);
    }
    Serial.printf("[ALERT] %s: water level at %.1f%%\n", level, waterPct);
}

void updateLedIndicator(unsigned long now) {
    if (currentAlert == "critical") {
        // Critical alert: solid steady illumination
        digitalWrite(LED_PIN, HIGH);
    } else if (currentAlert == "warning") {
        // Warning alert: 1 Hz blinking (500ms ON, 500ms OFF) to distinguish from critical
        digitalWrite(LED_PIN, (now / 500) % 2 == 0 ? HIGH : LOW);
    } else {
        // Normal state: LED OFF
        digitalWrite(LED_PIN, LOW);
    }
}

void evaluateThreshold(float waterPct) {
    String newAlert = "normal";

    if (waterPct >= CRIT_THRESHOLD_PCT) {
        newAlert = "critical";
    } else if (currentAlert == "critical" && waterPct >= (CRIT_THRESHOLD_PCT - HYSTERESIS_PCT)) {
        // Retain critical state within the critical hysteresis band
        newAlert = "critical";
    } else if (waterPct >= WARN_THRESHOLD_PCT) {
        newAlert = "warning";
    } else if (currentAlert == "warning" && waterPct >= (WARN_THRESHOLD_PCT - HYSTERESIS_PCT)) {
        // Retain warning state within the warning hysteresis band
        newAlert = "warning";
    } else {
        newAlert = "normal";
    }

    if (newAlert != currentAlert) {
        currentAlert = newAlert;
        publishAlert(currentAlert.c_str(), waterPct);
    }
}

void setup() {
    Serial.begin(115200);
    Serial.printf("CivicTwin-R %s - Water Level Monitor\n", DEVICE_ID);

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
    updateLedIndicator(now);

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

    if (now - lastReadTime >= READ_INTERVAL_MS) {
        lastReadTime = now;

        float distance = getMedianDistance();

        // Safe handling of invalid echo readings, timeouts, and out-of-range bounds
        if (distance < 0 || distance < SENSOR_MIN_CM || distance > SENSOR_MAX_CM) {
            failedReadings++;

            if (failedReadings >= MAX_FAILED) {
                // Reject invalid measurement: do NOT publish dummy 0.0 water level
                publishTelemetry(-1.0, -1.0, -1.0, "invalid");
                Serial.printf("[SENSOR] %d consecutive failures (out of range/timeout)\n", failedReadings);
            } else if (lastValidLevel >= 0) {
                float pct = (lastValidLevel / CONTAINER_HEIGHT_CM) * 100.0;
                evaluateThreshold(pct);
            }
        } else {
            failedReadings = 0;

            // Water depth (cm) = container reference height (cm) - measured distance (cm)
            float waterLevel = CONTAINER_HEIGHT_CM - distance;
            if (waterLevel < 0.0) waterLevel = 0.0;
            if (waterLevel > CONTAINER_HEIGHT_CM) waterLevel = CONTAINER_HEIGHT_CM;

            // Water level (%) = 100 * water depth / container reference height
            float waterPct = (waterLevel / CONTAINER_HEIGHT_CM) * 100.0;
            if (waterPct < 0.0) waterPct = 0.0;
            if (waterPct > 100.0) waterPct = 100.0;
            lastValidLevel = waterLevel;

            publishTelemetry(distance, waterLevel, waterPct, "valid");
            evaluateThreshold(waterPct);
        }
    }

    if (now - lastStatusTime >= STATUS_INTERVAL_MS) {
        lastStatusTime = now;

        JsonDocument doc;
        doc["device_id"]   = DEVICE_ID;
        doc["node_id"]     = NODE_ID;
        doc["wifi"]        = WiFi.status() == WL_CONNECTED;
        doc["mqtt"]        = mqttConnected;
        doc["uptime_sec"]  = millis() / 1000;
        doc["sequence"]    = sequence;
        doc["alert_state"] = currentAlert;
        doc["heap_free"]   = ESP.getFreeHeap();

        char payload[256];
        serializeJson(doc, payload, sizeof(payload));

        if (mqttConnected && mqttClient.connected()) {
            mqttClient.publish(TOPIC_ZONE_STATUS, payload);
            mqttClient.publish(TOPIC_NODE_STATUS, payload);
        }
        Serial.printf("[STATUS] uptime=%lus seq=%lu alert=%s heap=%u\n",
                      millis() / 1000, sequence, currentAlert.c_str(), ESP.getFreeHeap());
    }
}
