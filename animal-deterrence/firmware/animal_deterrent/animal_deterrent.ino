/*
 * Animal Deterrence - Ultrasonic proximity trigger
 *
 * HC-SR04 ultrasonic sensor watches the approach zone. When something comes
 * closer than TRIGGER_DISTANCE_CM, the buzzer sounds until it moves away.
 *
 * Wiring:
 *   HC-SR04 VCC  -> 5V
 *   HC-SR04 GND  -> GND
 *   HC-SR04 TRIG -> D9
 *   HC-SR04 ECHO -> D10
 *   Buzzer  +    -> D8
 *   Buzzer  -    -> GND
 *
 * Serial (9600 baud) prints one line per reading, e.g.
 *   DIST:24.3,ALERT:1
 *   DIST:-1,ALERT:0      (no echo / out of range)
 */

const uint8_t TRIG_PIN = 9;
const uint8_t ECHO_PIN = 10;
const uint8_t BUZZER_PIN = 8;

const float TRIGGER_DISTANCE_CM = 30.0;

// Set to true for a passive buzzer (needs a tone), false for an active buzzer.
const bool PASSIVE_BUZZER = false;
const unsigned int BUZZER_FREQ_HZ = 2500;

// Echo timeout ~ 4 m round trip; anything slower is treated as "nothing there".
const unsigned long ECHO_TIMEOUT_US = 25000UL;
const unsigned long READ_INTERVAL_MS = 100;

// Require a few consecutive close readings before alarming, to ignore glitches.
const uint8_t CONFIRM_READINGS = 2;

uint8_t closeCount = 0;
bool alarmOn = false;

float readDistanceCm() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  unsigned long duration = pulseIn(ECHO_PIN, HIGH, ECHO_TIMEOUT_US);
  if (duration == 0) {
    return -1.0;
  }
  return duration * 0.0343 / 2.0;
}

void setBuzzer(bool on) {
  if (PASSIVE_BUZZER) {
    if (on) {
      tone(BUZZER_PIN, BUZZER_FREQ_HZ);
    } else {
      noTone(BUZZER_PIN);
    }
  } else {
    digitalWrite(BUZZER_PIN, on ? HIGH : LOW);
  }
}

void setup() {
  Serial.begin(9600);
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(TRIG_PIN, LOW);
  setBuzzer(false);
  Serial.println("Animal deterrent ready. Trigger distance: 30 cm");
}

void loop() {
  float distance = readDistanceCm();
  bool close = distance > 0 && distance < TRIGGER_DISTANCE_CM;

  if (close) {
    if (closeCount < CONFIRM_READINGS) {
      closeCount++;
    }
  } else {
    closeCount = 0;
  }

  bool shouldAlarm = closeCount >= CONFIRM_READINGS;
  if (shouldAlarm != alarmOn) {
    alarmOn = shouldAlarm;
    setBuzzer(alarmOn);
  }

  Serial.print("DIST:");
  Serial.print(distance, 1);
  Serial.print(",ALERT:");
  Serial.println(alarmOn ? 1 : 0);

  delay(READ_INTERVAL_MS);
}
