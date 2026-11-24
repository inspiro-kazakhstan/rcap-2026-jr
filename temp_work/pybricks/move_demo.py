from pybricks.hubs import PrimeHub
from pybricks.pupdevices import Motor
from pybricks.parameters import Direction, Port
from pybricks.tools import wait, StopWatch
from usys import stdin
from uselect import poll

hub = PrimeHub()

LEFT_PORT = Port.A
RIGHT_PORT = Port.B

left = Motor(LEFT_PORT, Direction.CLOCKWISE)
right = Motor(RIGHT_PORT, Direction.COUNTERCLOCKWISE)

WATCHDOG_MS = 500

speed = 0

keyboard = poll()
keyboard.register(stdin)

buffer = ""
watchdog = StopWatch()

while True:
    while keyboard.poll(0):
        char = str(stdin.buffer.read(1), "utf-8")
 
        if char == "\n":
            parts = buffer.split()
            buffer = ""
 
            try:
                if "FWD" in parts[0]:
                    speed = 100
                elif "BWD" in parts[0]:
                    speed = -100
            except ValueError:
                pass
        else:
            buffer += char
        
    if watchdog.time() > WATCHDOG_MS:
        left.stop()
        right.stop()
        wait(10)
        continue
    
    left.run(speed)
    right.run(speed)