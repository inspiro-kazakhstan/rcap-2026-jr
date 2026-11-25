import sys
sys.coinit_flags = 0

import cv2
import time
import math
import threading
from contextlib import suppress

CAMERA_INDEX = 1
MAX_CAMERAS = 4
ARUCO_DICT = cv2.aruco.DICT_6X6_250

HEADING_OFFSET = 180.0
PRINT_EVERY = 1.0

pose_lock = threading.Lock()
poses = {}  # marker ID -> {x, y, angle}

def open_camera(index):
    if sys.platform == "win32":
        return cv2.VideoCapture(index, cv2.CAP_DSHOW)

def get_pose(marker_id):
    with pose_lock:
        pose = poses.get(marker_id)
        if pose is None:
            return None
        return dict(pose)

def marker_pose(points):
    center = points.mean(axis=0)
    top = (points[0] + points[1]) / 2
    angle = math.degrees(math.atan2(top[1] - center[1], top[0] - center[0]))
    return float(center[0]), float(center[1]), wrap(angle + HEADING_OFFSET)

def wrap(angle):
    return (angle + 180) % 360 - 180

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

detector = cv2.aruco.ArucoDetector(
    cv2.aruco.getPredefinedDictionary(ARUCO_DICT),
    cv2.aruco.DetectorParameters(),
)

last_print = {}
print("Камера работает. Q или Esc закрывают окно камеры.")

ROBOTS = {
    1: "Robot 1",
    2: "Robot 2",
    3: "Robot 3",
    4: "Robot 4",
    5: "Robot 5",
    6: "Robot 6",
    7: "Robot 7",
    8: "Robot 8",
}

try:
    while True:
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