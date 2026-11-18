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
from contextlib import suppress

import cv2
from bleak import BleakClient, BleakScanner

CAMERA_INDEX = 1
MAX_CAMERAS = 4
ARUCO_DICT = cv2.aruco.DICT_6X6_250

HEADING_OFFSET = 180.0  # маркер показывает направление, противоположное передней части робота
# marker ID: {Bluetooth hub name, pixel pyramid (x, y)}

ROBOTS = {
    1: {"hub": "1", "intro": (127, 69), "pyramid": (288, 72), "heart1": (250, 58), "heart2": (250, 58), "diamond": (243, 97)},
    2: {"hub": "inspiro 2", "intro": (542, 69), "pyramid": (377, 70), "heart1": (409, 63), "heart2": (409, 63), "diamond": (417, 103)},
    3: {"hub": "3", "intro": (103, 144), "pyramid": (215, 140), "heart1": (96, 130), "heart2": (96, 130), "diamond": (158, 174)},
    4: {"hub": "4", "intro": (545, 161), "pyramid": (454, 144), "heart1": (552, 140), "heart2": (552, 140), "diamond": (490, 190)},
    5: {"hub": "5", "intro": (99, 256), "pyramid": (164, 248), "heart1": (164, 248), "heart2": (164, 248), "diamond": (230, 280)},
    6: {"hub": "6", "intro": (566, 275), "pyramid": (498, 272), "heart1": (498, 272), "heart2": (484, 272), "diamond": (419, 280)},
    7: {"hub": "7", "intro": (109, 400), "pyramid": (109, 400), "heart1": (343, 371), "heart2": (343, 371), "diamond": (331, 384)},
    8: {"hub": "8", "intro": (554, 400), "pyramid": (554, 400), "heart1": (333, 136), "heart2": (333, 136), "diamond": (335, 36)}
}

SHAPES = {
    0: "intro",
    1: "pyramid",
    2: "heart1",
    3: "heart2",
    4: "diamond"
}

lights_pending = set()
lights_running = set()
lights_done = set()
arrived_for_shape = set()
lights_lock = threading.Lock()

curr_shape = 0

UART = "c5f50002-8280-46da-89f4-6d8051e4aeef"
CHUNK = 19
SEND_EVERY = 0.01
SEEN_MAX_AGE = 0.2
PRINT_EVERY = 1.0  # None disables position logging
WOW_PATH = "C:/Users/tolik/Documents/GitHub/rcap-2026-jr/audio/wow.mp3"
WAKA_WAKA_PATH = "C:/Users/tolik/Documents/Github/rcap-2026-jr/audio/waka waka.mp3"

stop_event = threading.Event()
pose_lock = threading.Lock()
poses = {}  # marker ID -> {x, y, angle, t}

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

def on_arrived(marker_id, arr_msg):
    if "ARRIVED" not in arr_msg:
        return

    with lights_lock:
        arrived_for_shape.add(marker_id)
        if len(arrived_for_shape) == len(ROBOTS):
            lights_pending.update(ROBOTS.keys())


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
                lights_done.add(marker_id)
                if len(lights_done) == len(ROBOTS):
                    if curr_shape != 0 or curr_shape != 2:
                        sound.playsound(WOW_PATH)
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
                        await send(client, "LIGHTS")
                        with lights_lock:
                            lights_pending.discard(marker_id)
                            lights_running.add(marker_id)
                        failures = 0
                        await asyncio.sleep(SEND_EVERY)
                        continue

                    pose = get_pose(marker_id)
                    if pose:
                        tx, ty = config[SHAPES[curr_shape]]
                        await send(client, f"{pose['x']:.0f} {pose['y']:.0f} {pose['angle']:.0f}")
                        await send(client, f"{tx} {ty}")
                        await send(client, f"{SHAPES[curr_shape]}")
                    else:
                        await send(client, "INTRO")
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
    music_thread = threading.Thread(target=play_music, daemon=True)
    music_thread.start()

    time.sleep(4)

    ble_thread = threading.Thread(target=run_ble, daemon=True)
    ble_thread.start()

    time.sleep(1)

    try:
        run_camera()
    finally:
        stop_event.set()
        ble_thread.join(timeout=5)