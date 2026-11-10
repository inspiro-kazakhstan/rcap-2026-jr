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
from contextlib import suppress

import cv2
from bleak import BleakClient, BleakScanner

CAMERA_INDEX = 1
MAX_CAMERAS = 4
ARUCO_DICT = cv2.aruco.DICT_6X6_250
HEADING_OFFSET = 0.0

ROBOTS = {
    7: {"hub": "7", "target": (154, 98)},
    8: {"hub": "8", "target": (460, 174)},
}

UART = "c5f50002-8280-46da-89f4-6d8051e4aeef"
CHUNK = 19
SEND_EVERY = 0.1
SEEN_MAX_AGE = 0.5
PRINT_EVERY = 1.0  # None disables position logging

stop_event = threading.Event()
pose_lock = threading.Lock()
poses = {}  # marker ID -> {x, y, angle, t}


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
                tx, ty = config["target"]
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
        text = bytes(data[1:]).decode(errors="ignore")
        if "rdy" in text:
            ready_events[marker_id].set()
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
                pose = get_pose(marker_id)
                if pose:
                    tx, ty = config["target"]
                    try:
                        await send(client, f"{pose['x']:.0f} {pose['y']:.0f} {pose['angle']:.0f}")
                        await send(client, f"{tx} {ty}")
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
    ble_thread = threading.Thread(target=run_ble, daemon=True)
    ble_thread.start()
    try:
        run_camera()
    finally:
        stop_event.set()
        ble_thread.join(timeout=5)
