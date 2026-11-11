/*
 * Smart Farm IoT Controller - Arduino Mega 2560 Firmware
 * Alappuzha Smart Farm (Pure IoT System)
 * 
 * Hardware Connections:
 * ================================================================
 * Sensor / Actuator       | Arduino Mega Pin | Notes
 * ------------------------+------------------+--------------------
 * Soil Moisture Sensor A0 | A0 (Analog)      | 0-100% soil moisture
 * Rain Drop Sensor A0     | A1 (Analog)      | Detects rainfall
 * LDR Light Sensor        | A2 (Analog)      | Sunlight / LUX level
 * Rain Tank TRIG          | Pin 9 (Digital)  | HC-SR04 / JSN-SR04T
 * Rain Tank ECHO          | Pin 10 (Digital) | mounted at tank top, facing down
 * DHT11/DHT22 Temp & Hum  | Pin 2 (Digital)  | 1-wire data bus
 * Motor driver, pump 1    | Pin 5 / Pin 7    | Pump 1, water (L298N motor A)
 * Motor driver, pump 2    | Pin 6 / Pin 8    | Pump 2, fertilizer (motor B, manual)
 * Status Indicator LED    | Pin 13 (Builtin) | Heartbeat toggle
 * Raspberry Pi 4 Link     | USB Serial       | 115200 baud
 * ================================================================
 */

#include <Arduino.h>
#include <EEPROM.h>

// --- PIN DEFINITIONS ---
const int PIN_SOIL_MOISTURE = A0;
const int PIN_RAIN_SENSOR   = A1;
const int PIN_LDR           = A2;
const int PIN_DHT           = 2;
const int PIN_HEARTBEAT_LED = 13;

// Pumps run from an L298N-style H-bridge with both inputs wired to the Mega:
// ON = one input HIGH and the other LOW, OFF = both LOW (no floating input, so the
// motor cannot creep). Direction per pump is set from the Pi with
// DIR:PUMP:FWD|REV / DIR:FERT:FWD|REV and kept in EEPROM.
struct Motor { uint8_t in_a, in_b; bool reverse; };
// Pins as wired on the farm (found with the Wiring app's input test)
Motor pump_motor = {5, 7, false};  // pump 1, water
Motor fert_motor = {6, 8, false};  // pump 2, fertilizer
const int EE_MAGIC = 0, EE_DIRS = 1;
const byte EE_MAGIC_VALUE = 0xB2;

// --- SYSTEM STATE & THRESHOLDS ---
// NAN until the DHT returns a valid reading; sent to the Pi as JSON null
float current_temperature = NAN;
float current_humidity    = NAN;
float current_soil        = 45.0;
int   current_rain        = 0;
int   current_light       = 70;
// Ultrasonic rainwater tank. cm / level stay NAN / -1 until a valid echo (sent as
// JSON null). empty_cm / full_cm: sensor-to-water distance when empty and full;
// the Pi overrides the defaults with TANK:<empty>:<full>.
struct Tank {
  uint8_t trig, echo;
  float empty_cm, full_cm;
  float cm;
  int level;
  unsigned long last_ok;
};
Tank tank = {9, 10, 100.0, 10.0, NAN, -1, 0};  // ~1 m deep tank

bool  pump_state = false;
bool  fert_state = false;
// Pumps switched on with a run time stop by themselves at these millis() (0 = no limit).
unsigned long pump_off_at = 0;
unsigned long fert_off_at = 0;
const unsigned long FERT_DEFAULT_S = 300; // FERT:ON without a time still stops after 5 min
bool  auto_mode  = true;
float dry_cutoff = 35.0; // Auto-start pump when soil drops below this
float stop_cutoff = 65.0; // Auto-stop pump when soil rises above this

unsigned long last_telemetry_time = 0;
unsigned long last_dht_read_time = 0;
unsigned long last_dht_ok_time = 0;
// DHT11s miss single reads now and then: keep the last good value for 2 minutes
// and retry a failed read after 1 s (the sensor's minimum interval)
const unsigned long DHT_STALE_MS = 120000;
unsigned long last_tank_read_time = 0;
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

// --- SERIAL COMMANDS ---
void process_command(String cmd);

// Reads whatever the Pi has sent. Also called while waiting between ultrasonic
// pings: the Mega's receive buffer holds only 64 bytes, and a burst of settings
// from the Pi would otherwise overflow it and lose commands.
void poll_serial() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (serial_buffer.length() > 0) {
        String cmd = serial_buffer;
        serial_buffer = "";
        process_command(cmd);
      }
    } else {
      serial_buffer += c;
      if (serial_buffer.length() > 64) serial_buffer = "";
    }
  }
}

// delay() that keeps reading serial commands
void wait_polling(unsigned long ms) {
  unsigned long start = millis();
  while (millis() - start < ms) {
    poll_serial();
    delay(1);
  }
}

// --- ULTRASONIC TANK SENSORS (HC-SR04 / JSN-SR04T) ---
// One ping: returns distance in cm, or -1 when there is no valid echo.
float ping_cm(const Tank &t) {
  // Cheap HC-SR04 clones can lock up with ECHO stuck HIGH after a ping with no
  // echo; pulling the line LOW resets them so the next ping works.
  if (digitalRead(t.echo) == HIGH) {
    pinMode(t.echo, OUTPUT);
    digitalWrite(t.echo, LOW);
    delay(2);
    pinMode(t.echo, INPUT);
    delay(10);
  }
  digitalWrite(t.trig, LOW);
  delayMicroseconds(2);
  digitalWrite(t.trig, HIGH);
  delayMicroseconds(20); // HC-SR04 needs >=10 us; waterproof JSN/AJ-SR04 modules want longer
  digitalWrite(t.trig, LOW);
  unsigned long us = pulseIn(t.echo, HIGH, 30000UL); // ~5 m max
  if (us == 0) return -1;
  float cm = us * 0.0343 / 2.0;
  return (cm >= 2.0 && cm <= 450.0) ? cm : -1;
}

// Median of 5 pings rejects ripples and stray echoes off the tank wall.
float read_tank_cm(const Tank &t) {
  float v[5];
  int n = 0;
  for (int i = 0; i < 5; i++) {
    float d = ping_cm(t);
    if (d > 0) v[n++] = d;
    wait_polling(60); // >=50 ms ping cycle: lets echoes die out; required by JSN-SR04T / AJ-SR04M
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

int tank_percent(const Tank &t, float cm) {
  float span = t.empty_cm - t.full_cm;
  if (span <= 1.0) return -1;
  float pct = (t.empty_cm - cm) * 100.0 / span;
  return (int)constrain(pct, 0, 100);
}

void update_tank(Tank &t) {
  float cm = read_tank_cm(t);
  if (cm > 0) {
    t.cm = cm;
    t.level = tank_percent(t, cm);
    t.last_ok = millis();
  } else if (millis() - t.last_ok > TANK_STALE_MS) {
    t.cm = NAN;
    t.level = -1;
  }
}

// --- MOTOR DRIVER ---
void motor_write(const Motor &m, bool on) {
  // Both LOW first so the bridge never sees both inputs HIGH while changing direction
  digitalWrite(m.in_a, LOW);
  digitalWrite(m.in_b, LOW);
  if (on) digitalWrite(m.reverse ? m.in_b : m.in_a, HIGH);
}

void set_pump(bool state) {
  pump_state = state;
  pump_off_at = 0;
  motor_write(pump_motor, pump_state);
  digitalWrite(PIN_HEARTBEAT_LED, pump_state ? HIGH : LOW);
}

void set_fert(bool state) {
  fert_state = state;
  fert_off_at = 0;
  motor_write(fert_motor, fert_state);
}

// Stops pumps whose run time is up (rollover-safe millis() comparison)
void check_pump_timers() {
  unsigned long now = millis();
  if (pump_off_at && (long)(now - pump_off_at) >= 0) set_pump(false);
  if (fert_off_at && (long)(now - fert_off_at) >= 0) set_fert(false);
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

  // 4. Rain tank level via ultrasonic distance (5-ping median), once per second
  if (millis() - last_tank_read_time > 1000) {
    update_tank(tank);
    last_tank_read_time = millis();
  }

  // 5. DHT Sensor (every 2 s; 1 s after a failed read)
  if (millis() - last_dht_read_time > 2000) {
    float t = 0, h = 0;
    bool ok = read_dht(t, h) && t >= 0 && t <= 60 && h >= 10 && h <= 100;
    if (ok) {
      current_temperature = t;
      current_humidity = h;
      last_dht_ok_time = millis();
    } else if (millis() - last_dht_ok_time > DHT_STALE_MS) {
      current_temperature = NAN;
      current_humidity = NAN;
    }
    last_dht_read_time = ok ? millis() : millis() - 1000;
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
  
  if (cmd == "PUMP:ON" || cmd == "PUMP_ON" || cmd == "MOTOR:ON" || cmd.startsWith("PUMP:ON:")) {
    // Optional run time: PUMP:ON:<seconds> stops by itself
    auto_mode = false;
    set_pump(true);
    long secs = cmd.startsWith("PUMP:ON:") ? cmd.substring(8).toInt() : 0;
    if (secs > 0) pump_off_at = millis() + secs * 1000UL;
    Serial.println(F("{\"ack\":\"PUMP_ON\",\"mode\":\"MANUAL\"}"));
  }
  else if (cmd == "PUMP:OFF" || cmd == "PUMP_OFF" || cmd == "MOTOR:OFF") {
    auto_mode = false;
    set_pump(false);
    Serial.println(F("{\"ack\":\"PUMP_OFF\",\"mode\":\"MANUAL\"}"));
  }
  else if (cmd == "FERT:ON" || cmd.startsWith("FERT:ON:")) {
    // FERT:ON:<seconds>; always time-limited (default 5 min, max 1 h)
    long secs = cmd.startsWith("FERT:ON:") ? cmd.substring(8).toInt() : 0;
    if (secs <= 0) secs = FERT_DEFAULT_S;
    if (secs > 3600) secs = 3600;
    set_fert(true);
    fert_off_at = millis() + secs * 1000UL;
    Serial.println(F("{\"ack\":\"FERT_ON\"}"));
  }
  else if (cmd == "FERT:OFF") {
    set_fert(false);
    Serial.println(F("{\"ack\":\"FERT_OFF\"}"));
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
    // Format: TANK:<empty_cm>:<full_cm>
    Tank &t = tank;
    int first_sep = cmd.indexOf(':');
    int second_sep = cmd.indexOf(':', first_sep + 1);
    if (second_sep > 0) {
      float e = cmd.substring(first_sep + 1, second_sep).toFloat();
      float f = cmd.substring(second_sep + 1).toFloat();
      if (f >= 2.0 && e > f + 1.0) {
        t.empty_cm = e;
        t.full_cm = f;
        if (!isnan(t.cm)) t.level = tank_percent(t, t.cm);
      }
      Serial.print(F("{\"ack\":\"TANK_SET\",\"empty_cm\":"));
      Serial.print(t.empty_cm, 1);
      Serial.print(F(",\"full_cm\":"));
      Serial.print(t.full_cm, 1);
      Serial.println(F("}"));
    }
  }
  else if (cmd.startsWith("DIR:PUMP:") || cmd.startsWith("DIR:FERT:")) {
    // DIR:PUMP:FWD (IN1 HIGH when on) or DIR:PUMP:REV (IN2 HIGH when on); same for FERT
    bool rev = cmd.endsWith(":REV");
    if (rev || cmd.endsWith(":FWD")) {
      bool is_pump = cmd.startsWith("DIR:PUMP:");
      Motor &m = is_pump ? pump_motor : fert_motor;
      if (m.reverse != rev) {
        m.reverse = rev;
        motor_write(m, is_pump ? pump_state : fert_state);  // keeps run timers
      }
      EEPROM.update(EE_MAGIC, EE_MAGIC_VALUE);
      EEPROM.update(EE_DIRS, (pump_motor.reverse ? 1 : 0) | (fert_motor.reverse ? 2 : 0));
    }
    Serial.print(F("{\"ack\":\"DIR_SET\",\"dir_pump\":\""));
    Serial.print(pump_motor.reverse ? F("REV") : F("FWD"));
    Serial.print(F("\",\"dir_fert\":\""));
    Serial.print(fert_motor.reverse ? F("REV") : F("FWD"));
    Serial.println(F("\"}"));
  }
  else if (cmd == "PING" || cmd == "STATUS") {
    send_telemetry();
  }
}

// --- TELEMETRY BROADCAST ---
void print_tank(const __FlashStringHelper *level_key, const __FlashStringHelper *cm_key, const Tank &t) {
  Serial.print(level_key);
  if (t.level < 0) Serial.print(F("null")); else Serial.print(t.level);
  Serial.print(cm_key);
  if (isnan(t.cm)) Serial.print(F("null")); else Serial.print(t.cm, 1);
}

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
  print_tank(F(",\"water_level\":"), F(",\"water_cm\":"), tank);
  Serial.print(F(",\"pump\":"));
  Serial.print(pump_state ? 1 : 0);
  Serial.print(F(",\"fert_pump\":"));
  Serial.print(fert_state ? 1 : 0);
  Serial.print(F(",\"dir_pump\":\""));
  Serial.print(pump_motor.reverse ? F("REV") : F("FWD"));
  Serial.print(F("\",\"dir_fert\":\""));
  Serial.print(fert_motor.reverse ? F("REV") : F("FWD"));
  Serial.print(F("\",\"mode\":\""));
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

  if (EEPROM.read(EE_MAGIC) == EE_MAGIC_VALUE) {
    byte r = EEPROM.read(EE_DIRS);
    pump_motor.reverse = r & 1;
    fert_motor.reverse = r & 2;
  }
  // All four driver inputs LOW (pumps off) from the moment they become outputs
  const uint8_t motor_pins[] = {pump_motor.in_a, pump_motor.in_b, fert_motor.in_a, fert_motor.in_b};
  for (uint8_t pin : motor_pins) {
    digitalWrite(pin, LOW);
    pinMode(pin, OUTPUT);
  }
  pinMode(PIN_HEARTBEAT_LED, OUTPUT);
  pinMode(PIN_DHT, INPUT_PULLUP);
  pinMode(tank.trig, OUTPUT);
  digitalWrite(tank.trig, LOW);
  pinMode(tank.echo, INPUT);

  set_pump(false);
  set_fert(false);

  Serial.println(F("{\"device\":\"Arduino Mega 2560\",\"status\":\"READY\",\"system\":\"IoT Agriculture\",\"baud\":115200}"));
}

void loop() {
  // 1. Process incoming commands from Raspberry Pi
  poll_serial();

  // 2. Read sensors and update pump logic
  sample_sensors();
  check_pump_timers();

  // 3. Emit JSON telemetry once per second
  unsigned long now = millis();
  if (now - last_telemetry_time >= 1000) {
    send_telemetry();
    last_telemetry_time = now;
  }
}
