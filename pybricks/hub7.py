from pybricks.hubs import PrimeHub
from pybricks.pupdevices import Motor
from pybricks.parameters import Port, Direction
from pybricks.tools import wait, StopWatch
from umath import atan2, sqrt, degrees
from usys import stdin
from uselect import poll
 
LEFT_PORT = Port.E
RIGHT_PORT = Port.F
MOTORS_REVERSED = False
WHEEL_DIAMETER = 56
AXLE_TRACK = 112
TURN_SIGN = 1
 
TOLERANCE = 15        # допуск попадания в цель, в пикселях кадра
WATCHDOG_MS = 500     # нет данных от компьютера дольше этого времени: стоп
 
FORWARD_SPEED = -150  # скорость движения (мм/с)
TURN_SPEED = 60       # скорость поворота корпуса (град/с)
TURN_ENTER_ANGLE = 15
TURN_EXIT_ANGLE = 12
KP_HEADING = 0.5      # небольшая P-коррекция курса во время движения
MAX_CORRECTION = 20   # предел коррекции курса (град/с)
PI = 3.14159
 
hub = PrimeHub()
left = Motor(LEFT_PORT, Direction.CLOCKWISE if MOTORS_REVERSED else Direction.COUNTERCLOCKWISE)
right = Motor(RIGHT_PORT, Direction.COUNTERCLOCKWISE if MOTORS_REVERSED else Direction.CLOCKWISE)
 
keyboard = poll()
keyboard.register(stdin)
 
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
 
buffer = ""
watchdog = StopWatch()

def normalize_angle(angle):
    return (angle + 180) % 360 - 180
 
def clamp(value, low, high):
    if value < low:
        return low
    if value > high:
        return high
    return value
 
 
print("rdy")
 
while True:
    while keyboard.poll(0):
        char = str(stdin.buffer.read(1), "utf-8")
 
        if char == "\n":
            parts = buffer.split()
            buffer = ""
 
            try:
                if len(parts) == 3:
                    curr_x = (float(parts[0]))
                    curr_y = float(parts[1])
                    curr_angle = float(parts[2])
                    have_pose = True
                    new_pose = True
                    watchdog.reset()
                elif len(parts) == 2:
                    target_x = float(parts[0]) - 2
                    target_y = float(parts[1]) - 2
            except ValueError:
                pass
        else:
            buffer += char
 
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
        turn_deg_s = clamp(KP_HEADING * error, -MAX_CORRECTION, MAX_CORRECTION)
    
    omega = turn_deg_s * PI / 180
    left_mm_s = speed_mm_s + omega * AXLE_TRACK / 2
    right_mm_s = speed_mm_s - omega * AXLE_TRACK / 2
    motor_scale = 360 / (PI * WHEEL_DIAMETER)
 
    left.run(left_mm_s * motor_scale)
    right.run(right_mm_s * motor_scale)