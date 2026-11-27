#include <Servo.h>

const int RELAY_PIN  = 2;        // реле (надпись) на пин 2
const int SERVO1_PIN = 5;        // первое серво на пин 5
const int SERVO2_PIN = 6;        // второе серво на пин 6
const int SERVO_DELAY = 500;     // скорость качания серво в мс

Servo servo1;
Servo servo2;

bool servo1On = false;
bool servo1Up = false;
unsigned long lastMove1 = 0;

bool servo2On = false;
bool servo2Up = false;
unsigned long lastMove2 = 0;

void setup() {
  Serial.begin(9600);
  pinMode(RELAY_PIN, OUTPUT);
  digitalWrite(RELAY_PIN, LOW);

  servo1.attach(SERVO1_PIN);
  servo1.write(0);

  servo2.attach(SERVO2_PIN);
  servo2.write(0);

  Serial.println("1 - надпись ВКЛ, 2 - надпись ВЫКЛ");
  Serial.println("3 - серво 1 ВКЛ, 4 - серво 1 ВЫКЛ");
  Serial.println("5 - серво 2 ВКЛ, 6 - серво 2 ВЫКЛ");
}

void loop() {
  if (Serial.available() > 0) {
    char key = Serial.read();

    switch (key) {
      case '1':
        digitalWrite(RELAY_PIN, HIGH);
        Serial.println("Надпись ВКЛ");
        break;
      case '2':
        digitalWrite(RELAY_PIN, LOW);
        Serial.println("Надпись ВЫКЛ");
        break;
      case '3':
        servo1On = true;
        Serial.println("Серво 1 ВКЛ");
        break;
      case '4':
        servo1On = false;
        servo1.write(0);
        Serial.println("Серво 1 ВЫКЛ");
        break;
      case '5':
        servo2On = true;
        Serial.println("Серво 2 ВКЛ");
        break;
      case '6':
        servo2On = false;
        servo2.write(0);
        Serial.println("Серво 2 ВЫКЛ");
        break;
    }
  }

  // качание первого серво
  if (servo1On && millis() - lastMove1 >= SERVO_DELAY) {
    lastMove1 = millis();
    servo1Up = !servo1Up;
    servo1.write(servo1Up ? 90 : 0);
  }

  // качание второго серво
  if (servo2On && millis() - lastMove2 >= SERVO_DELAY) {
    lastMove2 = millis();
    servo2Up = !servo2Up;
    servo2.write(servo2Up ? 90 : 0);
  }
}