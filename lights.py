from pybricks.pupdevices import DCMotor
from pybricks.parameters import Port
from pybricks.tools import wait

# robots number 8
# DC-мотор на порту A
motor = DCMotor(Port.D)

while True:
    # Вперёд 2 секунды
    motor.dc(100)       # мощность от -100 до 100 (%)
    wait(2000)

    # Остановка, пауза 1 секунда
    motor.stop()
    wait(1000)

    # Назад 2 секунды
    motor.dc(-100)
    wait(2000)

    # Остановка, пауза 1 секунда
    motor.stop()
    wait(1000)
