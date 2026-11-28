import sys
sys.coinit_flags = 0

try:
    from bleak.backends.winrt.util import allow_sta
    allow_sta()
except ImportError:
    pass

import asyncio
import math
import threading
import time
import playsound3 as sound
import serial
from voice import listen_for_start
from contextlib import suppress

import cv2
from bleak import BleakClient, BleakScanner

CAMERA_INDEX = 1
MAX_CAMERAS = 4
ARUCO_DICT = cv2.aruco.DICT_6X6_250

SIGN_ON = '1'
SIGN_OFF = '2'
SERVO1_ON = '3'
SERVO1_OFF = '4'

HEADING_OFFSET = 180.0

# Словарь со всеми роботами / Dictionary with all the robots
ROBOTS = {
    1: {"hub": "1", "pyramid": (382, 391), "heart1": (432, 356), "heart2": (431, 354), "heart3": (431, 356), "diamond": (431, 356), "umbrella": (436, 356), "bird": (508, 228), "tulip1": (527, 390), "tulip2": (527, 390), "outro1": (384, 404), "outro2": (384, 404)},
    2: {"hub": "inspiro 2", "pyramid": (248, 391), "heart1": (181, 356), "heart2": (181, 356), "heart3": (181, 356), "diamond": (181, 356), "umbrella": (189, 359), "bird": (122, 264), "tulip1": (134, 414), "tulip2": (134, 390), "outro1": (210, 408), "outro2": (210, 408)},
    3: {"hub": "3", "pyramid": (437, 258), "heart1": (520, 254), "heart2": (520, 254), "heart3": (520, 254),"diamond": (520, 254), "umbrella": (570, 166), "bird": (570, 166), "tulip1": (574, 173), "tulip2": (504, 245), "outro1": (504, 245), "outro2": (380, 283)},
    4: {"hub": "4", "pyramid": (191, 258), "heart1": (103, 254), "heart2": (103, 254), "heart3": (102, 272), "diamond": (103, 272), "umbrella": (40, 192), "bird": (40, 192), "tulip1": (39, 188), "tulip2": (151, 298), "outro1": (151, 298), "outro2": (228, 282)},
    5: {"hub": "5", "pyramid": (478, 155), "heart1": (431, 182), "heart2": (431, 182), "heart3": (431, 182), "diamond": (431, 182), "umbrella": (431, 177), "bird": (431, 177), "tulip1": (428, 173), "tulip2": (429, 172), "outro1": (429, 172), "outro2": (372, 164)},
    6: {"hub": "6", "pyramid": (165, 155), "heart1": (202, 182), "heart2": (202, 182), "heart3": (202, 182), "diamond": (202, 182), "umbrella": (200, 185), "bird": (200, 185), "tulip1": (213, 170), "tulip2": (213, 170), "outro1": (213, 170), "outro2": (234, 171)},
    7: {"hub": "7", "pyramid": (511, 77), "heart1": (510, 93), "heart2": (510, 102), "heart3": (318, 114), "diamond": (318, 114), "umbrella": (302, 54), "bird": (302, 67), "tulip1": (313, 70), "tulip2": (313, 69), "outro1": (364, 67) , "outro2": (364, 67)},
    8: {"hub": "8", "pyramid": (125, 77), "heart1": (304, 93), "heart2": (313, 287), "heart3": (313, 308), "diamond": (321, 374), "umbrella": (318, 369), "bird": (304, 142), "tulip1": (322, 278), "tulip2": (322, 278), "outro1": (229, 80), "outro2": (229, 80)}
}

LIGHTS_ROBOTS = set(ROBOTS)

SHAPES = {
    0: "pyramid",
    1: "heart1",
    2: "heart2",
    3: "heart3",
    4: "diamond",
    5: "umbrella",
    6: "bird",
    7: "tulip1",
    8: "tulip2",
    9: "outro1",
    10: "outro2"
}

lights_pending = set()
lights_running = set()
lights_done = set()
arrived_for_shape = set()
ever_seen = set()
lights_lock = threading.Lock()

curr_shape = 0

UART = "c5f50002-8280-46da-89f4-6d8051e4aeef"
CHUNK = 19
SEND_EVERY = 0.01
SEEN_MAX_AGE = 0.2
PRINT_EVERY = 1.0  # None disables position logging
WOW_PATH = "C:/Users/tolik/Documents/GitHub/rcap-2026-jr/audio/wow.mp3"
WAKA_WAKA_PATH = "C:/Users/tolik/Documents/Github/rcap-2026-jr/audio/waka waka.mp3"

LOST_AFTER = 0.8
SEARCH_RETRY_SECONDS = 2.5
MAX_SEARCH_ATTEMPTS = 10

stop_event = threading.Event()
pose_lock = threading.Lock()
poses = {}

#Инициализирует COM-порт / Initializes the COM port
try:
    serial_port = serial.Serial('COM3', 9600)
    print("Порт инициализирован!")  
except Exception as e:
    print(f"Не удалось инициализировать порт: {e}")
    serial_port = None

def send_serial_signal(signal):
    if serial_port:
        try:
            serial_port.write(signal)
        except Exception as e:
            print(f"Ошибка при отправке данных в Serial: {e}")

def play_music():
    if not stop_event.is_set():
        sound.playsound(WAKA_WAKA_PATH)

def wrap(angle):
    return (angle + 180) % 360 - 180

def marker_pose(points):
    center = points.mean(axis=0)
    top = (points[0] + points[1]) / 2
    angle = math.degrees(math.atan2(top[1] - center[1], top[0] - center[0]))
    return float(center[0]), float(center[1]), wrap(angle + HEADING_OFFSET)
    
def get_pose(marker_id):
    with pose_lock:
        pose = poses.get(marker_id)
        if pose is None or time.monotonic() - pose["t"] > SEEN_MAX_AGE:
            return None
        return dict(pose)

def get_pose_age(marker_id):
    with pose_lock:
        pose = poses.get(marker_id)
        if pose is None:
            return None
        return time.monotonic() - pose["t"]

def on_arrived(marker_id, arr_msg):
    if "ARRIVED" not in arr_msg:
        return

    with lights_lock:
        arrived_for_shape.add(marker_id)
        if len(arrived_for_shape) == len(ROBOTS):
            lights_pending.update(LIGHTS_ROBOTS)
            for i in range(4):
                send_serial_signal(b'1')
                threading.Timer(0.5, lambda: send_serial_signal(b'2')).start()

def voice_worker():
    while not start_signal.is_set():
        result = listen_for_start()
        if result and "open" in result.lower():
            start_signal.set()
            break

def open_camera(index):
    if sys.platform == "win32":
        return cv2.VideoCapture(index, cv2.CAP_DSHOW)


def run_camera():
    camera = open_camera(CAMERA_INDEX)
    if not camera.isOpened():
        camera.release()
        camera = None
        for index in range(MAX_CAMERAS):
            trial = open_camera(index)
            if trial.isOpened():
                camera = trial
                break
            trial.release()

    if camera is None:
        print("Ошибка: камера не открылась!")
        return

    detector = cv2.aruco.ArucoDetector(
        cv2.aruco.getPredefinedDictionary(ARUCO_DICT),
        cv2.aruco.DetectorParameters(),
    )

    last_print = {}
    print("Камера работает. Q или Esc закрывают окно камеры.")

    try:
        while not stop_event.is_set():
            ok, frame = camera.read()
            if not ok or frame is None:
                time.sleep(0.03)
                if cv2.waitKey(1) & 0xFF in (27, ord("q"), ord("Q")):
                    break
                continue

            corners, ids, _ = detector.detectMarkers(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
            if ids is not None:
                cv2.aruco.drawDetectedMarkers(frame, corners, ids)
                for raw_id, corner in zip(ids.flatten(), corners):
                    global marker_id
                    marker_id = int(raw_id)
                    if marker_id not in ROBOTS:
                        continue
                    x, y, angle = marker_pose(corner.reshape(4, 2))
                    with pose_lock:
                        poses[marker_id] = {
                            "x": x, "y": y, "angle": angle, "t": time.monotonic()
                        }
                    cv2.putText(
                        frame, f"{marker_id}: {angle:.0f}deg",
                        (int(x), max(20, int(y) - 15)), cv2.FONT_HERSHEY_SIMPLEX,
                        0.5, (0, 255, 0), 2,
                    )

            now = time.monotonic()
            for marker_id, config in ROBOTS.items():
                tx, ty = config[SHAPES[curr_shape]]
                cv2.circle(frame, (int(tx), int(ty)), 12, (0, 0, 255), 2)
                cv2.putText(frame, str(marker_id), (int(tx) + 14, int(ty)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
                if PRINT_EVERY is not None and now - last_print.get(marker_id, 0) >= PRINT_EVERY:
                    pose = get_pose(marker_id)
                    if pose:
                        print(f"Робот {marker_id}: x={pose['x']:.0f} y={pose['y']:.0f} "
                              f"угол={pose['angle']:.1f}")
                        last_print[marker_id] = now

            cv2.imshow("Robots", frame)
            if cv2.waitKey(1) & 0xFF in (27, ord("q"), ord("Q")):
                break
            with suppress(cv2.error):
                if cv2.getWindowProperty("Robots", cv2.WND_PROP_VISIBLE) < 1:
                    break
    finally:
        camera.release()
        cv2.destroyAllWindows()
        for _ in range(5):
            cv2.waitKey(30)
        print("Камера выключена.")


def make_data_handler(marker_id):
    def on_data(_, data):
        if not data or data[0] != 0x01:
            return
        global curr_shape
        text = bytes(data[1:]).decode(errors="ignore")

        if "rdy" in text:
            ready_events[marker_id].set()
        if "ARRIVED" in text:
            on_arrived(marker_id, text)
        if "lights rdy" in text:
            with lights_lock:
                if marker_id in LIGHTS_ROBOTS:
                    lights_done.add(marker_id)
                if lights_done == LIGHTS_ROBOTS:
                    if curr_shape != 1 and curr_shape != 2 and curr_shape != 7 and curr_shape != 9 and curr_shape != 10:
                        sound.playsound(WOW_PATH)
                        send_serial_signal(b'3')
                        send_serial_signal(b'5')
                        threading.Timer(3.0, send_serial_signal, args=(b'4',)).start()
                        threading.Timer(3.0, send_serial_signal, args=(b'6',)).start()
                    lights_done.clear()
                    lights_running.clear()
                    arrived_for_shape.clear()
                    curr_shape = min(curr_shape + 1, len(SHAPES) - 1)

        for line in text.splitlines():
            line = line.strip()
            if line and line != "rdy":
                print(f"Хаб {ROBOTS[marker_id]['hub']}: {line}")
    return on_data


async def send(client, text):
    data = (text + "\n").encode()
    for offset in range(0, len(data), CHUNK):
        await client.write_gatt_char(UART, b"\x06" + data[offset:offset + CHUNK], response=True)


async def control_robot(marker_id, config):
    hub_name = config["hub"]
    ready = asyncio.Event()
    ready_events[marker_id] = ready
    device = await BleakScanner.find_device_by_name(hub_name, timeout=10)
    if device is None:
        print(f"Хаб {hub_name} не найден")
        return

    async with BleakClient(device) as client:
        await client.start_notify(UART, make_data_handler(marker_id))
        await client.write_gatt_char(UART, b"\x01", response=True)
        await asyncio.wait_for(ready.wait(), 20)
        print(f"Хаб {hub_name} готов")

        failures = 0
        ever_seen = False
        search_attempts = 0
        next_search_at = 0.0
        try:
            while not stop_event.is_set():
                with lights_lock:
                    is_running_lights = marker_id in lights_running
                    should_run_lights = marker_id in lights_pending

                if is_running_lights:
                    await asyncio.sleep(SEND_EVERY)
                    continue

                try:
                    if should_run_lights:
                        with lights_lock:
                            lights_pending.discard(marker_id)
                            lights_running.add(marker_id)

                        await send(client, "LIGHTS")
                        failures = 0
                        await asyncio.sleep(SEND_EVERY)
                        continue

                    pose = get_pose(marker_id)

                    if pose:
                        ever_seen = True
                        search_attempts = 0
                        next_search_at = 0.0

                        tx, ty = config[SHAPES[curr_shape]]
                        await send(client, f"{pose['x']:.0f} {pose['y']:.0f} {pose['angle']:.0f}")
                        await send(client, f"{tx} {ty}")
                        await send(client, f"{SHAPES[curr_shape]}")

                    elif not ever_seen:
                        await send(client, "INTRO")

                    else:
                        age = get_pose_age(marker_id)
                        now = time.monotonic()

                        if (
                            age is not None
                            and age >= LOST_AFTER
                            and search_attempts < MAX_SEARCH_ATTEMPTS
                            and now >= next_search_at
                        ):
                            await send(client, "SEARCH")
                            search_attempts += 1
                            next_search_at = now + SEARCH_RETRY_SECONDS
                    failures = 0
                except Exception as exc:
                    failures += 1
                    print(f"Хаб {hub_name}: ошибка отправки ({failures}/5): {type(exc).__name__}: {exc}")
                    if failures >= 5:
                        print(f"Хаб {hub_name} не принимает данные; перезапусти программу на хабе.")
                        break
                    await asyncio.sleep(0.5)
                    continue
                await asyncio.sleep(SEND_EVERY)
        finally:
            with suppress(Exception):
                await client.write_gatt_char(UART, b"\x00", response=True)


ready_events = {}


async def ble():
    await asyncio.gather(*(control_robot(marker_id, config)
                           for marker_id, config in ROBOTS.items()))


def run_ble():
    try:
        asyncio.run(ble())
    except Exception as exc:
        print(f"Ошибка Bluetooth: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    start_signal = threading.Event()

    ble_thread = threading.Thread(target=run_ble, daemon=True)

    voice_thread = threading.Thread(target=voice_worker, daemon=True)
    voice_thread.start()

    start_signal.wait(timeout=6.0)
    start_signal.set()

    try:
        send_serial_signal(b'1')
        ble_thread.start()
        run_camera()
    finally:
        stop_event.set()
        send_serial_signal(b'2')
        ble_thread.join(timeout=5)