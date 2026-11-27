from pybricks.hubs import PrimeHub
from pybricks.pupdevices import Motor, DCMotor
from pybricks.parameters import Port, Direction
from pybricks.tools import wait, StopWatch
from umath import atan2, sqrt, degrees
from usys import stdin
from uselect import poll, POLLIN
 
LEFT_PORT = Port.A
RIGHT_PORT = Port.B
LIGHT_PORT = Port.F
MOTORS_REVERSED = False
WHEEL_DIAMETER = 56
AXLE_TRACK = 112
TURN_SIGN = 1
 
TOLERANCE = 20        # допуск попадания в цель, в пикселях кадра
WATCHDOG_MS = 500     # нет данных от компьютера дольше этого времени: стоп

FORWARD_SPEED = 260  # скорость движения (мм/с)
TURN_SPEED = 60       # скорость поворота корпуса (град/с)
TURN_ENTER_ANGLE = 15
TURN_EXIT_ANGLE = 12
KP_HEADING = 0.5      # небольшая P-коррекция курса во время движения
MAX_CORRECTION = 20   # предел коррекции курса (град/с)
PI = 3.14159

SEARCH_MOTOR_SPEED = 140  # motor degrees/second
SEARCH_BACK_MS = 350
SEARCH_TURN_MS = 300
SEARCH_FORWARD_MS = 650
 
hub = PrimeHub()
left = Motor(LEFT_PORT, Direction.CLOCKWISE if MOTORS_REVERSED else Direction.COUNTERCLOCKWISE)
right = Motor(RIGHT_PORT, Direction.COUNTERCLOCKWISE if MOTORS_REVERSED else Direction.CLOCKWISE)
light = DCMotor(LIGHT_PORT)
 
keyboard = poll()
keyboard.register(stdin, POLLIN)

hub_name = hub.system.info()["name"]
curr_x = 0.0
curr_y = 0.0
curr_angle = 0.0
target_x = None
target_y = None
have_pose = False
new_pose = False
at_target = False
aligning = False
turn_direction = 1
intro_mode = "on"
searching = False
search_step = 0
search_watch = StopWatch()

buffer = ""
watchdog = StopWatch()

shape = None

def normalize_angle(angle):
    return (angle + 180) % 360 - 180
 
def clamp(value, low, high):
    if value < low:
        return low
    if value > high:
        return high
    return value

def intro():
    if intro_mode == "on":
        left.run(FORWARD_SPEED)
        right.run(FORWARD_SPEED)

def turn_on_lights(shape):
    if "pyramid" in shape:
        light.dc(-100)
        wait(2000)

        light.stop()
        wait(1000)

    elif "heart3" in shape:
        for i in range(4):
            light.dc(100)
            wait(500)

            light.stop()
            wait(500)

    elif "diamond" in shape:
        light.dc(-100)
        wait(2000)

        light.stop()
        wait(1000)
    
    elif "umbrella" in shape:
        light.dc(100)
        wait(2000)
        
        light.stop()

    elif "bird" in shape:
        for i in range(2):
            light.dc(-100)
            wait(2000)

            light.stop()
            wait(1000)
    
    elif "tulip2" in shape:
        light.dc(100)
        wait(2000)

        light.stop()
        wait(1000)
    
    print("lights rdy")

if hub_name == "4" or hub_name == "6" or hub_name == "8":
    light.dc(100)
    wait(3000)
    light.stop()
elif hub_name == "inspiro 2" or hub_name == "1" or hub_name == "3" or hub_name == "5" or hub_name == "7":
    light.dc(-100)
    wait(3000)
    light.stop()

while not hub.system.info()["host_connected_ble"]:
    wait(6)

if hub_name == "4" or hub_name == "6" or hub_name == "8":
    light.dc(100)
    wait(3000)
    light.stop()
    print("rdy")
elif hub_name == "inspiro 2" or hub_name == "1" or hub_name == "3" or hub_name == "5" or hub_name == "7":
    light.dc(-100)
    wait(3000)
    light.stop()
    print("rdy")
 
while True:
    while keyboard.poll(0):
        char = str(stdin.buffer.read(1), "utf-8")
 
        if char == "\n":
            parts = buffer.split()
            buffer = ""
 
            try:
                if len(parts) == 3:
                    searching = False
                    intro_mode = "off"
                    curr_x = float(parts[0])
                    curr_y = float(parts[1])
                    curr_angle = float(parts[2])
                    have_pose = True
                    new_pose = True
                    watchdog.reset()
                elif len(parts) == 2:
                    intro_mode = "off"
                    target_x = float(parts[0])
                    target_y = float(parts[1])
                elif len(parts) == 1:
                    if "LIGHTS" in parts[0]:
                        intro_mode = "off"
                        turn_on_lights(shape)
                    elif "INTRO" in parts[0]:
                        intro()
                    elif "SEARCH" in parts[0]:
                        intro_mode = "off"
                        searching = True
                        search_step = 0
                        search_watch.reset()
                    else:
                        intro_mode = "off"
                        new_shape = str(parts[0])
                        if new_shape != shape:
                            shape = new_shape
                            at_target = False
            except ValueError:
                pass
        else:
            buffer += char
    
    if searching:
        elapsed = search_watch.time()

        if search_step == 0:
            left.run(-SEARCH_MOTOR_SPEED)
            right.run(-SEARCH_MOTOR_SPEED)
            if elapsed >= SEARCH_BACK_MS:
                left.stop()
                right.stop()
                search_step = 1
                search_watch.reset()

        elif search_step == 1:
            left.run(-SEARCH_MOTOR_SPEED)
            right.run(SEARCH_MOTOR_SPEED)
            if elapsed >= SEARCH_TURN_MS:
                left.stop()
                right.stop()
                search_step = 2
                search_watch.reset()

        elif search_step == 2:
            left.run(SEARCH_MOTOR_SPEED)
            right.run(SEARCH_MOTOR_SPEED)
            if elapsed >= SEARCH_FORWARD_MS:
                left.stop()
                right.stop()
                searching = False

        wait(10)
        continue

    if intro_mode == "off":
        if watchdog.time() > WATCHDOG_MS or not have_pose or target_x is None:
            left.stop()
            right.stop()
            new_pose = False
            aligning = False
            wait(10)
            continue
 
    if not new_pose:
        wait(10)
        continue
 
    new_pose = False
 
    dx = target_x - curr_x
    dy = target_y - curr_y
    distance = sqrt(dx * dx + dy * dy)
 
    if distance <= TOLERANCE:
        left.stop()
        right.stop()
        aligning = False
        if not at_target:
            at_target = True
            print("ARRIVED")
        continue
 
    at_target = False
 
    target_angle = (degrees(atan2(dy, dx)))
    error = normalize_angle(target_angle - curr_angle)
 
    if not aligning and abs(error) > TURN_ENTER_ANGLE:
        aligning = True
        turn_direction = 1 if error > 0 else -1
    elif aligning and abs(error) <= TURN_EXIT_ANGLE:
        aligning = False

    if aligning:
        speed_mm_s = 0

        # Чем меньше ошибка, тем медленнее поворот
        turn_magnitude = min(TURN_SPEED, max(3, 1.5 * (abs(error) - TURN_EXIT_ANGLE)))
        turn_deg_s = TURN_SIGN * turn_direction * turn_magnitude
    else:
        speed_mm_s = FORWARD_SPEED
        turn_deg_s = TURN_SIGN * clamp(KP_HEADING * error, -MAX_CORRECTION, MAX_CORRECTION)
    
    omega = turn_deg_s * PI / 180
    left_mm_s = speed_mm_s + omega * AXLE_TRACK / 2
    right_mm_s = speed_mm_s - omega * AXLE_TRACK / 2
    motor_scale = 360 / (PI * WHEEL_DIAMETER)
 
    left.run(left_mm_s * motor_scale)
    right.run(right_mm_s * motor_scale)
