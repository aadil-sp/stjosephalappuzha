/*
 * Smart Farm IoT Controller - Arduino Mega 2560 Firmware
 * St. Joseph Alappuzha Project
 * 
 * Hardware Connections:
 * ================================================================
 * Sensor / Actuator       | Arduino Mega Pin | Notes
 * ------------------------+------------------+--------------------
 * Soil Moisture Sensor A0 | A0 (Analog)      | 0-100% moisture
 * Rain Drop Sensor A0     | A1 (Analog)      | Detects rainfall
 * LDR Light Sensor        | A2 (Analog)      | Sunlight level
 * Water Tank Level Sensor | A3 (Analog)      | Float / depth level
 * DHT11/DHT22 Temp & Hum  | Pin 2 (Digital)  | 1-wire data bus
 * Water Pump Relay IN     | Pin 8 (Digital)  | Relays pump 12V/5V
 * Deterrence Buzzer / ALM | Pin 9 (PWM/Dig)  | Audio deterrence
 * Status Indicator LED    | Pin 13 (Builtin) | Heartbeat toggle
 * Raspberry Pi 4 Link     | USB Serial       | 115200 baud
 * ================================================================
 */

#include <Arduino.h>

// --- PIN DEFINITIONS ---
const int PIN_SOIL_MOISTURE = A0;
const int PIN_RAIN_SENSOR   = A1;
const int PIN_LDR           = A2;
const int PIN_WATER_LEVEL   = A3;
const int PIN_DHT           = 2;
const int PIN_PUMP_RELAY    = 8;
const int PIN_BUZZER        = 9;
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
float current_temperature = 28.0;
float current_humidity    = 65.0;
float current_soil        = 45.0;
int   current_rain        = 0;
int   current_light       = 70;
int   current_water_level = 80;

bool  pump_state = false;
bool  auto_mode  = true;
float dry_cutoff = 35.0; // Auto-start pump when soil drops below this
float stop_cutoff = 65.0; // Auto-stop pump when soil rises above this

unsigned long last_telemetry_time = 0;
unsigned long last_dht_read_time = 0;
String serial_buffer = "";

// --- BIT-BANG DHT11 / DHT22 SENSOR DRIVER ---
// Self-contained, works without requiring external library installs
bool read_dht(float &temp_out, float &hum_out) {
  uint8_t data[5] = {0, 0, 0, 0, 0};
  
  pinMode(PIN_DHT, OUTPUT);
  digitalWrite(PIN_DHT, LOW);
  delay(20); // Start signal for DHT11 (>18ms)
  digitalWrite(PIN_DHT, HIGH);
  delayMicroseconds(30);
  pinMode(PIN_DHT, INPUT_PULLUP);

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
    // High pulse > 40us means bit '1', else '0'
    if ((micros() - pulse_start) > 40) {
      data[i / 8] |= (1 << (7 - (i % 8)));
    }
  }

  // Verify checksum
  if (data[4] != ((data[0] + data[1] + data[2] + data[3]) & 0xFF)) {
    return false;
  }

  // Determine if DHT11 or DHT22
  if (data[1] == 0 && data[3] == 0) {
    // Typical DHT11 integer readings
    hum_out = data[0];
    temp_out = data[2];
  } else {
    // DHT22 float readings
    hum_out = ((data[0] << 8) | data[1]) * 0.1;
    temp_out = (((data[2] & 0x7F) << 8) | data[3]) * 0.1;
    if (data[2] & 0x80) temp_out = -temp_out;
  }
  return true;
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
  // Map raw 1023->0% to 300->100%
  int mapped_soil = map(raw_soil, 1023, 300, 0, 100);
  current_soil = constrain(mapped_soil, 0, 100);

  // 2. Rain Sensor: Analog (Wet ~ 200, Dry ~ 1023)
  int raw_rain = analogRead(PIN_RAIN_SENSOR);
  current_rain = (raw_rain < 600) ? 1 : 0;

  // 3. LDR Ambient Light (0-100%)
  int raw_ldr = analogRead(PIN_LDR);
  current_light = map(raw_ldr, 0, 1023, 0, 100);

  // 4. Water Tank Level (0-100%)
  int raw_water = analogRead(PIN_WATER_LEVEL);
  current_water_level = map(raw_water, 0, 700, 0, 100);
  current_water_level = constrain(current_water_level, 0, 100);

  // 5. DHT Sensor (Read every 2 seconds)
  if (millis() - last_dht_read_time > 2000) {
    float t = 0, h = 0;
    if (read_dht(t, h)) {
      if (t >= 0 && t <= 60) current_temperature = t;
      if (h >= 10 && h <= 100) current_humidity = h;
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
  else if (cmd == "BUZZ:ON" || cmd == "BUZZER:ON") {
    tone(PIN_BUZZER, 2000);
    Serial.println(F("{\"ack\":\"BUZZER_ON\"}"));
  }
  else if (cmd == "BUZZ:OFF" || cmd == "BUZZER:OFF") {
    noTone(PIN_BUZZER);
    Serial.println(F("{\"ack\":\"BUZZER_OFF\"}"));
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
  else if (cmd == "PING" || cmd == "STATUS") {
    send_telemetry();
  }
}

// --- TELEMETRY BROADCAST ---
void send_telemetry() {
  Serial.print(F("{\"temp\":"));
  Serial.print(current_temperature, 1);
  Serial.print(F(",\"humidity\":"));
  Serial.print(current_humidity, 1);
  Serial.print(F(",\"soil\":"));
  Serial.print(current_soil, 1);
  Serial.print(F(",\"rain\":"));
  Serial.print(current_rain);
  Serial.print(F(",\"light\":"));
  Serial.print(current_light);
  Serial.print(F(",\"water_level\":"));
  Serial.print(current_water_level);
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
  pinMode(PIN_BUZZER, OUTPUT);
  pinMode(PIN_HEARTBEAT_LED, OUTPUT);
  pinMode(PIN_DHT, INPUT_PULLUP);

  set_pump(false);
  noTone(PIN_BUZZER);

  // Beep briefly on startup
  tone(PIN_BUZZER, 2400, 150);
  delay(200);

  Serial.println(F("{\"device\":\"Arduino Mega 2560\",\"status\":\"READY\",\"baud\":115200}"));
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
