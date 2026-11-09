/*
 * Smart Farm IoT Controller - Arduino Mega 2560 Firmware
 * St. Joseph Alappuzha Project (Pure IoT System)
 * 
 * Hardware Connections:
 * ================================================================
 * Sensor / Actuator       | Arduino Mega Pin | Notes
 * ------------------------+------------------+--------------------
 * Soil Moisture Sensor A0 | A0 (Analog)      | 0-100% soil moisture
 * Rain Drop Sensor A0     | A1 (Analog)      | Detects rainfall
 * LDR Light Sensor        | A2 (Analog)      | Sunlight / LUX level
 * Ultrasonic Tank TRIG    | Pin 9 (Digital)  | HC-SR04 / JSN-SR04T
 * Ultrasonic Tank ECHO    | Pin 10 (Digital) | mounted at tank top, facing down
 * DHT11/DHT22 Temp & Hum  | Pin 2 (Digital)  | 1-wire data bus
 * Water Pump Relay IN     | Pin 8 (Digital)  | Controls water pump
 * Status Indicator LED    | Pin 13 (Builtin) | Heartbeat toggle
 * Raspberry Pi 4 Link     | USB Serial       | 115200 baud
 * ================================================================
 */

#include <Arduino.h>

// --- PIN DEFINITIONS ---
const int PIN_SOIL_MOISTURE = A0;
const int PIN_RAIN_SENSOR   = A1;
const int PIN_LDR           = A2;
const int PIN_TANK_TRIG     = 9;
const int PIN_TANK_ECHO     = 10;
const int PIN_DHT           = 2;
const int PIN_PUMP_RELAY    = 8;
const int PIN_HEARTBEAT_LED = 13;

// Set relay active logic (most Arduino relay modules are Active LOW)
#define RELAY_ACTIVE_LOW 1

#if RELAY_ACTIVE_LOW
  #define RELAY_ON  LOW
  #define RELAY_OFF HIGH
#else
  #define RELAY_ON  HIGH
  #define RELAY_OFF LOW
#endif

// --- SYSTEM STATE & THRESHOLDS ---
// NAN until the DHT returns a valid reading; sent to the Pi as JSON null
float current_temperature = NAN;
float current_humidity    = NAN;
float current_soil        = 45.0;
int   current_rain        = 0;
int   current_light       = 70;
// Ultrasonic tank level: NAN / -1 until a valid echo; sent to the Pi as JSON null
float current_water_cm    = NAN;
int   current_water_level = -1;

// Tank calibration: sensor-to-water distance when empty and when full (cm).
// Defaults suit a ~1 m deep tank; the Pi overrides them with TANK:<empty>:<full>.
float tank_empty_cm = 100.0;
float tank_full_cm  = 10.0;

bool  pump_state = false;
bool  auto_mode  = true;
float dry_cutoff = 35.0; // Auto-start pump when soil drops below this
float stop_cutoff = 65.0; // Auto-stop pump when soil rises above this

unsigned long last_telemetry_time = 0;
unsigned long last_dht_read_time = 0;
unsigned long last_dht_ok_time = 0;
const unsigned long DHT_STALE_MS = 10000; // Report null after 10s without a good read
unsigned long last_tank_read_time = 0;
unsigned long last_tank_ok_time = 0;
const unsigned long TANK_STALE_MS = 5000; // Report null after 5s without an echo
String serial_buffer = "";

// --- BIT-BANG DHT11 / DHT22 SENSOR DRIVER ---
bool read_dht(float &temp_out, float &hum_out) {
  uint8_t data[5] = {0, 0, 0, 0, 0};
  
  pinMode(PIN_DHT, OUTPUT);
  digitalWrite(PIN_DHT, LOW);
  delay(20); // Start signal for DHT11 (>18ms)
  digitalWrite(PIN_DHT, HIGH);
  delayMicroseconds(30);
  pinMode(PIN_DHT, INPUT_PULLUP);
  pinMode(PIN_TANK_TRIG, OUTPUT);
  pinMode(PIN_TANK_ECHO, INPUT);
  digitalWrite(PIN_TANK_TRIG, LOW);

  // Wait for sensor response: LOW (80us) then HIGH (80us)
  unsigned long timeout = micros();
  while (digitalRead(PIN_DHT) == HIGH) {
    if (micros() - timeout > 100) return false;
  }
  timeout = micros();
  while (digitalRead(PIN_DHT) == LOW) {
    if (micros() - timeout > 100) return false;
  }
  timeout = micros();
  while (digitalRead(PIN_DHT) == HIGH) {
    if (micros() - timeout > 100) return false;
  }

  // Read 40 bits (5 bytes)
  for (int i = 0; i < 40; i++) {
    timeout = micros();
    while (digitalRead(PIN_DHT) == LOW) {
      if (micros() - timeout > 100) return false;
    }
    unsigned long pulse_start = micros();
    timeout = micros();
    while (digitalRead(PIN_DHT) == HIGH) {
      if (micros() - timeout > 100) return false;
    }
    if ((micros() - pulse_start) > 40) {
      data[i / 8] |= (1 << (7 - (i % 8)));
    }
  }

  // Checksum validation
  if (data[4] != ((data[0] + data[1] + data[2] + data[3]) & 0xFF)) {
    return false;
  }

  if (data[1] == 0 && data[3] == 0) {
    // DHT11
    hum_out = data[0];
    temp_out = data[2];
  } else {
    // DHT22
    hum_out = ((data[0] << 8) | data[1]) * 0.1;
    temp_out = (((data[2] & 0x7F) << 8) | data[3]) * 0.1;
    if (data[2] & 0x80) temp_out = -temp_out;
  }
  return true;
}

// --- ULTRASONIC TANK SENSOR (HC-SR04 / JSN-SR04T) ---
// One ping: returns distance in cm, or -1 when there is no valid echo.
float ping_cm() {
  // Cheap HC-SR04 clones can lock up with ECHO stuck HIGH after a ping with no
  // echo; pulling the line LOW resets them so the next ping works.
  if (digitalRead(PIN_TANK_ECHO) == HIGH) {
    pinMode(PIN_TANK_ECHO, OUTPUT);
    digitalWrite(PIN_TANK_ECHO, LOW);
    delay(2);
    pinMode(PIN_TANK_ECHO, INPUT);
    delay(10);
  }
  digitalWrite(PIN_TANK_TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(PIN_TANK_TRIG, HIGH);
  delayMicroseconds(20); // HC-SR04 needs >=10 us; waterproof JSN/AJ-SR04 modules want longer
  digitalWrite(PIN_TANK_TRIG, LOW);
  unsigned long us = pulseIn(PIN_TANK_ECHO, HIGH, 30000UL); // ~5 m max
  if (us == 0) return -1;
  float cm = us * 0.0343 / 2.0;
  return (cm >= 2.0 && cm <= 450.0) ? cm : -1;
}

// Median of 5 pings rejects ripples and stray echoes off the tank wall.
float read_tank_cm() {
  float v[5];
  int n = 0;
  for (int i = 0; i < 5; i++) {
    float d = ping_cm();
    if (d > 0) v[n++] = d;
    delay(60); // >=50 ms ping cycle: lets echoes die out; required by JSN-SR04T / AJ-SR04M
  }
  if (n < 3) return -1;
  for (int i = 1; i < n; i++) {
    float k = v[i];
    int j = i - 1;
    while (j >= 0 && v[j] > k) { v[j + 1] = v[j]; j--; }
    v[j + 1] = k;
  }
  return v[n / 2];
}

int tank_percent(float cm) {
  float span = tank_empty_cm - tank_full_cm;
  if (span <= 1.0) return -1;
  float pct = (tank_empty_cm - cm) * 100.0 / span;
  return (int)constrain(pct, 0, 100);
}

// --- RELAY CONTROLLER ---
void set_pump(bool state) {
  pump_state = state;
  digitalWrite(PIN_PUMP_RELAY, pump_state ? RELAY_ON : RELAY_OFF);
  digitalWrite(PIN_HEARTBEAT_LED, pump_state ? HIGH : LOW);
}

// --- SENSOR SAMPLING ---
void sample_sensors() {
  // 1. Soil Moisture: Capacitive/Resistive (Dry ~ 850-1023, Wet ~ 250-400)
  int raw_soil = analogRead(PIN_SOIL_MOISTURE);
  int mapped_soil = map(raw_soil, 1023, 300, 0, 100);
  current_soil = constrain(mapped_soil, 0, 100);

  // 2. Rain Sensor: Analog (Wet < 600)
  int raw_rain = analogRead(PIN_RAIN_SENSOR);
  current_rain = (raw_rain < 600) ? 1 : 0;

  // 3. LDR Ambient Light (0-100%)
  int raw_ldr = analogRead(PIN_LDR);
  current_light = map(raw_ldr, 0, 1023, 0, 100);

  // 4. Water Tank Level via ultrasonic distance (5-ping median, every 1 s)
  if (millis() - last_tank_read_time > 1000) {
    float cm = read_tank_cm();
    if (cm > 0) {
      current_water_cm = cm;
      current_water_level = tank_percent(cm);
      last_tank_ok_time = millis();
    } else if (millis() - last_tank_ok_time > TANK_STALE_MS) {
      current_water_cm = NAN;
      current_water_level = -1;
    }
    last_tank_read_time = millis();
  }

  // 5. DHT Sensor (Sample every 2 seconds)
  if (millis() - last_dht_read_time > 2000) {
    float t = 0, h = 0;
    if (read_dht(t, h)) {
      if (t >= 0 && t <= 60) current_temperature = t;
      if (h >= 10 && h <= 100) current_humidity = h;
      last_dht_ok_time = millis();
    } else if (millis() - last_dht_ok_time > DHT_STALE_MS) {
      current_temperature = NAN;
      current_humidity = NAN;
    }
    last_dht_read_time = millis();
  }

  // Automatic Irrigation Logic
  if (auto_mode) {
    if (current_soil < dry_cutoff && !pump_state) {
      set_pump(true);
    } else if (current_soil >= stop_cutoff && pump_state) {
      set_pump(false);
    }
  }
}

// --- COMMAND PROCESSOR ---
void process_command(String cmd) {
  cmd.trim();
  cmd.toUpperCase();
  
  if (cmd == "PUMP:ON" || cmd == "PUMP_ON" || cmd == "MOTOR:ON") {
    auto_mode = false;
    set_pump(true);
    Serial.println(F("{\"ack\":\"PUMP_ON\",\"mode\":\"MANUAL\"}"));
  }
  else if (cmd == "PUMP:OFF" || cmd == "PUMP_OFF" || cmd == "MOTOR:OFF") {
    auto_mode = false;
    set_pump(false);
    Serial.println(F("{\"ack\":\"PUMP_OFF\",\"mode\":\"MANUAL\"}"));
  }
  else if (cmd == "MODE:AUTO" || cmd == "AUTO") {
    auto_mode = true;
    Serial.println(F("{\"ack\":\"MODE_AUTO\"}"));
  }
  else if (cmd == "MODE:MANUAL" || cmd == "MANUAL") {
    auto_mode = false;
    Serial.println(F("{\"ack\":\"MODE_MANUAL\"}"));
  }
  else if (cmd.startsWith("CUTOFF:")) {
    // Format: CUTOFF:35:65
    int first_sep = cmd.indexOf(':');
    int second_sep = cmd.indexOf(':', first_sep + 1);
    if (second_sep > 0) {
      dry_cutoff = cmd.substring(first_sep + 1, second_sep).toFloat();
      stop_cutoff = cmd.substring(second_sep + 1).toFloat();
      Serial.print(F("{\"ack\":\"CUTOFF_SET\",\"dry\":"));
      Serial.print(dry_cutoff);
      Serial.print(F(",\"stop\":"));
      Serial.print(stop_cutoff);
      Serial.println(F("}"));
    }
  }
  else if (cmd.startsWith("TANK:")) {
    // Format: TANK:<empty_cm>:<full_cm>  e.g. TANK:100:10
    int first_sep = cmd.indexOf(':');
    int second_sep = cmd.indexOf(':', first_sep + 1);
    if (second_sep > 0) {
      float e = cmd.substring(first_sep + 1, second_sep).toFloat();
      float f = cmd.substring(second_sep + 1).toFloat();
      if (f >= 2.0 && e > f + 1.0) {
        tank_empty_cm = e;
        tank_full_cm = f;
        if (!isnan(current_water_cm)) current_water_level = tank_percent(current_water_cm);
      }
      Serial.print(F("{\"ack\":\"TANK_SET\",\"empty_cm\":"));
      Serial.print(tank_empty_cm, 1);
      Serial.print(F(",\"full_cm\":"));
      Serial.print(tank_full_cm, 1);
      Serial.println(F("}"));
    }
  }
  else if (cmd == "PING" || cmd == "STATUS") {
    send_telemetry();
  }
}

// --- TELEMETRY BROADCAST ---
void send_telemetry() {
  Serial.print(F("{\"temp\":"));
  if (isnan(current_temperature)) Serial.print(F("null")); else Serial.print(current_temperature, 1);
  Serial.print(F(",\"humidity\":"));
  if (isnan(current_humidity)) Serial.print(F("null")); else Serial.print(current_humidity, 1);
  Serial.print(F(",\"soil\":"));
  Serial.print(current_soil, 1);
  Serial.print(F(",\"rain\":"));
  Serial.print(current_rain);
  Serial.print(F(",\"light\":"));
  Serial.print(current_light);
  Serial.print(F(",\"water_level\":"));
  if (current_water_level < 0) Serial.print(F("null")); else Serial.print(current_water_level);
  Serial.print(F(",\"water_cm\":"));
  if (isnan(current_water_cm)) Serial.print(F("null")); else Serial.print(current_water_cm, 1);
  Serial.print(F(",\"pump\":"));
  Serial.print(pump_state ? 1 : 0);
  Serial.print(F(",\"mode\":\""));
  Serial.print(auto_mode ? F("AUTO") : F("MANUAL"));
  Serial.print(F("\",\"dry_cutoff\":"));
  Serial.print(dry_cutoff, 1);
  Serial.print(F(",\"stop_cutoff\":"));
  Serial.print(stop_cutoff, 1);
  Serial.println(F("}"));
}

void setup() {
  // Serial Interface to Raspberry Pi
  Serial.begin(115200);

  pinMode(PIN_PUMP_RELAY, OUTPUT);
  pinMode(PIN_HEARTBEAT_LED, OUTPUT);
  pinMode(PIN_DHT, INPUT_PULLUP);

  set_pump(false);

  Serial.println(F("{\"device\":\"Arduino Mega 2560\",\"status\":\"READY\",\"system\":\"IoT Agriculture\",\"baud\":115200}"));
}

void loop() {
  // 1. Process incoming commands from Raspberry Pi
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (serial_buffer.length() > 0) {
        process_command(serial_buffer);
        serial_buffer = "";
      }
    } else {
      serial_buffer += c;
      if (serial_buffer.length() > 64) serial_buffer = "";
    }
  }

  // 2. Read sensors and update pump logic
  sample_sensors();

  // 3. Emit JSON telemetry once per second
  unsigned long now = millis();
  if (now - last_telemetry_time >= 1000) {
    send_telemetry();
    last_telemetry_time = now;
  }
}
