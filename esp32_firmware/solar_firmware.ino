#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <Adafruit_INA219.h>
#include <PZEM004Tv30.h>

// --- UPDATE THESE ---
const char* ssid = "YOUR_WIFI_NAME";
const char* password = "YOUR_WIFI_PASSWORD";
const char* serverUrl = "http://YOUR_PC_IP:8000/api/esp-sync/";

// --- PINS ---
Adafruit_INA219 inaSolar(0x40);  
Adafruit_INA219 inaBattery(0x41); 
PZEM004Tv30 pzem(Serial2, 16, 17);

#define PIN_VOLT_DIVIDER 34

// RELAYS (Active LOW)
#define PIN_RELAY_HOME   26  // Relay 1 (Dual Ch)
#define PIN_RELAY_SELL   27  // Relay 2 (Dual Ch)
#define PIN_RELAY_IMPORT 25  // Relay 3 (Single Ch) - NEW

float voltageFactor = 0.0033; 

void setup() {
  Serial.begin(115200);

  // 1. RELAY SETUP
  pinMode(PIN_RELAY_HOME, OUTPUT);
  pinMode(PIN_RELAY_SELL, OUTPUT);
  pinMode(PIN_RELAY_IMPORT, OUTPUT);

  // START ALL OFF (Active Low -> High is Off)
  digitalWrite(PIN_RELAY_HOME, HIGH); 
  digitalWrite(PIN_RELAY_SELL, HIGH); 
  digitalWrite(PIN_RELAY_IMPORT, HIGH); 

  // 2. SENSORS
  Wire.begin();
  if (!inaSolar.begin()) Serial.println("Solar INA fail");
  if (!inaBattery.begin()) Serial.println("Bat INA fail");

  // 3. WIFI
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) delay(500);
  Serial.println("WiFi Connected!");
}

void loop() {
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    JsonDocument doc, response;

    // A. READ SENSORS
    float solarW = inaSolar.getPower_mW() / 1000.0;
    float batOutW = inaBattery.getPower_mW() / 1000.0;
    float v = pzem.voltage(); float c = pzem.current();
    float gridW = (!isnan(v) && !isnan(c)) ? v * c : 0.0;
    
    int adc = analogRead(PIN_VOLT_DIVIDER);
    float batPct = map(adc * voltageFactor * 4.3 * 100, 1180, 1280, 0, 100);

    // B. SEND DATA
    doc["solar_w"] = solarW;
    doc["bat_out_w"] = batOutW;
    doc["grid_w"] = gridW;
    doc["bat_pct"] = constrain(batPct, 0, 100);

    String jsonStr;
    serializeJson(doc, jsonStr);

    http.begin(serverUrl);
    http.addHeader("Content-Type", "application/json");
    int code = http.POST(jsonStr);

    // C. RECEIVE COMMANDS
    if (code > 0) {
      String payload = http.getString();
      deserializeJson(response, payload);
      
      bool homeActive = response["relay_home"];
      bool sellActive = response["relay_grid"];
      bool importActive = response["relay_import"]; // <--- NEW

      // APPLY LOGIC (Active LOW: True = LOW)
      digitalWrite(PIN_RELAY_HOME, homeActive ? LOW : HIGH);
      digitalWrite(PIN_RELAY_SELL, sellActive ? LOW : HIGH);
      digitalWrite(PIN_RELAY_IMPORT, importActive ? LOW : HIGH);
      
      Serial.printf("Home:%d Sell:%d Import:%d\n", homeActive, sellActive, importActive);
    }
    http.end();
  }
  delay(2000);
}