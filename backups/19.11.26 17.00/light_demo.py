from pybricks.hubs import PrimeHub
from pybricks.pupdevices import DCMotor
from pybricks.parameters import Port
from pybricks.tools import wait

LIGHT_PORT = Port.F

hub = PrimeHub()
light = DCMotor(LIGHT_PORT)

while True:
    light.dc(100)
    wait(2000)

    light.stop()
    wait(1000)

    light.dc(-100)
    wait(2000)

    light.stop()
    wait(1000)