/*
 * CivicTwin-R — ESP32 Firmware
 * Water-Level Monitoring with HC-SR04 Ultrasonic Sensor
 *
 * Reads distance from an HC-SR04 sensor, calculates water depth,
 * evaluates local thresholds with hysteresis, and publishes telemetry over MQTT.
 *
 * Pin Connections:
 *   HC-SR04 TRIG -> GPIO 5
 *   HC-SR04 ECHO -> GPIO 18 (use 2.2k/3.3k resistor divider on physical HW for 3.3V)
 *   HC-SR04 VCC  -> 5V (VIN)
 *   HC-SR04 GND  -> GND
 *   Status LED   -> GPIO 2
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <time.h>

// WiFi Configuration
const char* WIFI_SSID     = "Wokwi-GUEST";
const char* WIFI_PASSWORD = "";

// MQTT Broker Configuration
const char* MQTT_BROKER    = "localhost";
const int   MQTT_PORT      = 1883;
const char* MQTT_CLIENT_ID = "civictwin_node01";
const char* MQTT_USER      = "";
const char* MQTT_PASS      = "";

// MQTT Topics
const char* TOPIC_TELEMETRY = "civictwin/v1/zones/zone_01/telemetry";
const char* TOPIC_STATUS    = "civictwin/v1/zones/zone_01/status";
const char* TOPIC_ALERTS    = "civictwin/v1/zones/zone_01/alerts";

// Device Identification
const char* DEVICE_ID = "node_01";
const char* ZONE_ID   = "zone_01";

// Sensor Geometry and Pins
const int   TRIG_PIN            = 5;
const int   ECHO_PIN            = 18;
const int   LED_PIN             = 2;
const float CONTAINER_HEIGHT_CM = 30.0;
const float SENSOR_MIN_CM       = 2.0;
const float SENSOR_MAX_CM       = 400.0;
const float SPEED_OF_SOUND      = 0.0343;

// Intervals
const unsigned long READ_INTERVAL_MS   = 5000;
const unsigned long RECONNECT_DELAY_MS = 5000;
const unsigned long WIFI_TIMEOUT_MS    = 10000;
const unsigned long STATUS_INTERVAL_MS = 30000;

// Thresholds and Hysteresis
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
    doc["zone_id"]     = ZONE_ID;
    doc["device_id"]   = DEVICE_ID;
    doc["alert_level"] = level;
    doc["water_pct"]   = waterPct;
    doc["threshold"]   = (strcmp(level, "critical") == 0) ? CRIT_THRESHOLD_PCT : WARN_THRESHOLD_PCT;
    doc["timestamp"]   = getISO8601Timestamp();

    char payload[256];
    serializeJson(doc, payload, sizeof(payload));

    if (mqttConnected && mqttClient.connected()) {
        mqttClient.publish(TOPIC_ALERTS, payload);
    }
    Serial.printf("[ALERT] %s: water level at %.1f%%\n", level, waterPct);
}

void evaluateThreshold(float waterPct) {
    String newAlert = "normal";

    if (waterPct >= CRIT_THRESHOLD_PCT) {
        newAlert = "critical";
    } else if (waterPct >= WARN_THRESHOLD_PCT) {
        newAlert = "warning";
    } else if (currentAlert == "warning" && waterPct >= (WARN_THRESHOLD_PCT - HYSTERESIS_PCT)) {
        newAlert = "warning";
    } else if (currentAlert == "critical" && waterPct >= (CRIT_THRESHOLD_PCT - HYSTERESIS_PCT)) {
        newAlert = "critical";
    }

    if (newAlert != currentAlert) {
        currentAlert = newAlert;
        if (currentAlert == "critical" || currentAlert == "warning") {
            publishAlert(currentAlert.c_str(), waterPct);
            digitalWrite(LED_PIN, HIGH);
        } else {
            publishAlert("normal", waterPct);
            digitalWrite(LED_PIN, LOW);
        }
    }
}

void setup() {
    Serial.begin(115200);
    Serial.println("CivicTwin-R Node 01 - Water Level Monitor");

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

        if (distance < 0 || distance < SENSOR_MIN_CM || distance > SENSOR_MAX_CM) {
            failedReadings++;

            if (failedReadings >= MAX_FAILED) {
                publishTelemetry(0, 0, 0, "invalid");
                Serial.printf("[SENSOR] %d consecutive failures\n", failedReadings);
            } else if (lastValidLevel >= 0) {
                float pct = (lastValidLevel / CONTAINER_HEIGHT_CM) * 100.0;
                evaluateThreshold(pct);
            }
        } else {
            failedReadings = 0;

            float waterLevel = CONTAINER_HEIGHT_CM - distance;
            if (waterLevel < 0) waterLevel = 0;
            if (waterLevel > CONTAINER_HEIGHT_CM) waterLevel = CONTAINER_HEIGHT_CM;

            float waterPct = (waterLevel / CONTAINER_HEIGHT_CM) * 100.0;
            lastValidLevel = waterLevel;

            publishTelemetry(distance, waterLevel, waterPct, "valid");
            evaluateThreshold(waterPct);
        }
    }

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
