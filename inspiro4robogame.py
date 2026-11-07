from pybricks.hubs import PrimeHub
from pybricks.pupdevices import Motor
from pybricks.parameters import Port, Direction
from pybricks.tools import wait

hub = PrimeHub()

right_motor = Motor(Port.E, Direction.COUNTERCLOCKWISE)
left_motor = Motor(Port.F, Direction.COUNTERCLOCKWISE)

left_motor.control.limits(acceleration=1000)
right_motor.control.limits(acceleration=1000)

Kp = 1.5
WHEEL_DIAMETER = 5.6  
DEGREES_PER_CM = 360 / (3.14159 * WHEEL_DIAMETER) 

def pid_straight_cm(target_angle, speed, distance_cm, returnbot=False):
    """Движение по прямой на заданное расстояние с ПИД-регулятором"""
    left_motor.reset_angle(0)
    right_motor.reset_angle(0)
    target_degrees = distance_cm * DEGREES_PER_CM
    
    while (abs(left_motor.angle()) + abs(right_motor.angle())) / 2 < target_degrees:
        current_angle = hub.imu.heading()
        error = target_angle - current_angle
        pid_value = (Kp * error) * 10
        
        if not returnbot:
            left_motor.run(-speed + pid_value)
            right_motor.run(speed + pid_value)
        else:
            left_motor.run(speed + pid_value)
            right_motor.run(-speed + pid_value)
            
        wait(10)
        
    left_motor.stop()
    right_motor.stop()

def turn(target_angle):
    """Поворот на заданный абсолютный угол по гироскопу"""
    while abs(hub.imu.heading() - target_angle) > 2:
        error = target_angle - hub.imu.heading()
        speed = max(min(error * 4, 280), -280)
        left_motor.run(speed)
        right_motor.run(speed)
        wait(10)
    left_motor.stop()
    right_motor.stop()

# 1. Сообщаем компьютеру, что хаб запущен и готов принимать команды
print("rdy")

while True:
    try:
        line = input().strip()
        if not line:
            continue
        if line == "stop":
            break
            
        parts = line.split()
        # Проверяем, что передано 3 параметра (например: "50 90 10")
        if len(parts) >= 1:
            distance_1 = float(parts[0])  # Первая дистанция (50 см)

            pid_straight_cm(0, 250, distance_1, True)  # Едем 90 см  
            wait(6200)                          
            print(f"done heading: {hub.imu.heading()}")
        else:
            print("err: unknown command")
    except Exception as e:
        print(f"err: {e}")
        
    print("rdy")
        
    # 3. Снова сигнализируем ПК о готовности к следующей команд