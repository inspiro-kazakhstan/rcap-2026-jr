from pybricks.hubs import PrimeHub
from pybricks.pupdevices import Motor
from pybricks.parameters import Port, Direction
from pybricks.robotics import DriveBase
from pybricks.tools import wait, StopWatch
from umath import atan2, sqrt, cos, radians, degrees
from usys import stdin
from uselect import poll
 
LEFT_PORT = Port.A
RIGHT_PORT = Port.B
MOTORS_REVERSED = False
WHEEL_DIAMETER = 56
AXLE_TRACK = 112
TURN_SIGN = 1
 
TOLERANCE = 15        # допуск попадания в цель, в пикселях кадра
WATCHDOG_MS = 500     # нет данных от компьютера дольше этого времени: стоп
 
MAX_SPEED = 200       # максимальная скорость (мм/с)
MAX_TURN_RATE = 200   # максимальная скорость поворота (град/с)
 
# ПИД выравнивания (угол): выход в град/с
KP_TURN = 1.5
KI_TURN = 0.3
KD_TURN = 0.1
I_MAX_TURN = 30       # предел интегральной части (град/с)
I_ZONE = 30           # интеграл копится только если ошибка угла меньше этого (градусы)
delta_angle = 10       # мёртвая зона по углу (градусы)
 
# ПИД движения прямо (расстояние до цели в пикселях): выход в мм/с
KP_SPEED = 1.2
KI_SPEED = 0.1
KD_SPEED = 0.15
I_MAX_SPEED = 30      # предел интегральной части (мм/с)
 
hub = PrimeHub()
left = Motor(LEFT_PORT, Direction.CLOCKWISE if MOTORS_REVERSED else Direction.COUNTERCLOCKWISE)
right = Motor(RIGHT_PORT, Direction.COUNTERCLOCKWISE if MOTORS_REVERSED else Direction.CLOCKWISE)
robot = DriveBase(left, right, WHEEL_DIAMETER, AXLE_TRACK)
robot.settings(straight_speed=MAX_SPEED, turn_rate=MAX_TURN_RATE)
 
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
turn_dir = 1
 
turn_i = 0.0
speed_i = 0.0
prev_error = None
prev_distance = None
 
buffer = ""
watchdog = StopWatch()
clock = StopWatch()
last_time = 0
 
 
def normalize_angle(angle):
    return (angle + 180) % 360 - 180
 
 
def clamp(value, low, high):
    if value < low:
        return low
    if value > high:
        return high
    return value
 
 
def reset_pid():
    global turn_i, speed_i, prev_error, prev_distance
    turn_i = 0.0
    speed_i = 0.0
    prev_error = None
    prev_distance = None
 
 
print("rdy")
 
while True:
    while keyboard.poll(0):
        char = str(stdin.buffer.read(1), "utf-8")
 
        if char == "\n":
            parts = buffer.split()
            buffer = ""
 
            try:
                if len(parts) == 3:
                    curr_x = float(parts[0])
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
        robot.stop()
        reset_pid()
        new_pose = False
        wait(10)
        continue
 
    if not new_pose:
        wait(10)
        continue
 
    new_pose = False
 
    now = clock.time()
    dt = (now - last_time) / 1000
    last_time = now
 
    if dt <= 0 or dt > 0.5:
        reset_pid()
        dt = 0.1
 
    dx = target_x - curr_x
    dy = target_y - curr_y
    distance = sqrt(dx * dx + dy * dy)
 
    if distance <= TOLERANCE:
        robot.stop()
        reset_pid()
        if not at_target:
            at_target = True
            print("ARRIVED")
        continue
 
    at_target = False
 
    target_angle = degrees(atan2(dy, dx))
    error = normalize_angle(target_angle - curr_angle)
 
    if abs(error) < delta_angle:
        error = 0
    elif abs(error) > 135:
        error = turn_dir * abs(error)
    else:
        turn_dir = 1 if error > 0 else -1
 
    if error == 0 or abs(error) > I_ZONE or (prev_error is not None and error * prev_error < 0):
        turn_i = 0.0
    else:
        turn_i = clamp(turn_i + KI_TURN * error * dt, -I_MAX_TURN, I_MAX_TURN)
 
    turn_d = 0.0
    if prev_error is not None and abs(error - prev_error) < 90:
        turn_d = KD_TURN * (error - prev_error) / dt
 
    prev_error = error
 
    turn_rate = TURN_SIGN * clamp(KP_TURN * error + turn_i + turn_d, -MAX_TURN_RATE, MAX_TURN_RATE)
 
    alignment = max(0.0, cos(radians(error)))
 
    if alignment > 0.9:
        speed_i = clamp(speed_i + KI_SPEED * distance * dt, 0, I_MAX_SPEED)
 
    speed_d = 0.0
    if prev_distance is not None:
        speed_d = KD_SPEED * (distance - prev_distance) / dt
 
    prev_distance = distance
 
    speed = clamp(KP_SPEED * distance + speed_i + speed_d, 0, MAX_SPEED) * alignment
 
    robot.drive(speed, turn_rate)