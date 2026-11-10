# ==========================================
# САМОЕ ПЕРВОЕ: НАСТРОЙКА COM ДЛЯ BLE (ДО OPENCV!)
# ==========================================
import sys
sys.coinit_flags = 0

try:
    from bleak.backends.winrt.util import allow_sta
    allow_sta()
except ImportError:
    pass

# Теперь остальные импорты
import asyncio
from collections import deque
from contextlib import suppress
import math
import os
import re
import threading
import time
import cv2
import numpy as np
import playsound3
from bleak import BleakScanner, BleakClient

# ==========================================
# НАСТРОЙКИ: ЗДЕСЬ ТЫ МЕНЯЕШЬ ФИГУРЫ И ПЕСНЮ
# ==========================================

# Список хабов. В каждом шаге фигуры столько чисел, сколько хабов,
# в том же порядке. Имя = Bluetooth-имя хаба.
# Все 8 роботов. Порядок хабов = порядок чисел в каждом шаге фигуры.
HUB_NAMES = ["1", "inspiro 2", "3", "4", "5", "6", "7", "8"]

# ARUCO-МАРКЕРЫ НА РОБОТАХ.
# Слева НОМЕР маркера (число, без кавычек), справа любое имя.
# Номер маркера это НЕ имя хаба! Как узнать номер: покажи маркер камере,
# в консоли появится «Вижу маркер №...».
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

# ----------------------------------
# ФИГУРЫ (движение роботов)
# ----------------------------------
# Фигура = номер: список шагов. Шаг = [число для каждого хаба].
# Команды в консоли:
#   вперед   — все фигуры по порядку (1, 2, 3...)
#   1 или 2  — только одна эта фигура
#   стоп     — остановить и выйти
FIGURES = {
    # 8 чисел в шаге: по одному на каждый хаб, в порядке HUB_NAMES.
    1: [
        [b"20", b"50", b"100", b"145", b"145", b"100", b"50", b"20"],
    ],

    # 2: [
    #     [b"150", b"150", b"150", b"150", b"150", b"150", b"150", b"150"],
    # ],
}

# Чем заканчивается команда хабу. Обычно b"\r\n".
# Если хаб отвечает «err: unknown command», попробуй b"\n" или b"".
COMMAND_END = b"\r\n"

# ----------------------------------
# УЗОРЫ НА ПОЛЕ (камера видит, что роботы выстроились в рисунок)
# ----------------------------------
# Узор = {номер маркера: (колонка, строка)} на сетке 12x12.
# Когда ВСЕ маркеры узора стоят на своих клетках, играет wow.mp3.
PATTERNS_ENABLED = True
PATTERN_TOLERANCE = 1   # на сколько клеток маркер может отличаться (0 = точно)
WOW_SOUND = "wow"       # запасной звук, если для узора нет своего файла

# Своя песня для каждого узора: имя файла БЕЗ расширения (mp3, wav, ogg...)
# в папке песни. Нет такого файла, играет WOW_SOUND.
PATTERN_SOUNDS = {
    "Pyramid": "pyramid",
    "Heart": "heart",
    "Sun": "sun",
    "Butterfly": "butterfly",
    "Bird": "bird",
    "Diamond": "diamond",
}

# True = при сборке узора играет главная песня 67.mp3 вместо звуков выше
PATTERN_USE_MAIN_SONG = False

PATTERNS = {
    "Pyramid": {
        1: (2, 9), 2: (3, 7), 3: (4, 5), 4: (5, 3),
        5: (8, 3), 6: (9, 5), 7: (10, 7), 8: (11, 9),
    },
    "Heart": {
        1: (7, 12), 2: (4, 9), 3: (1, 4), 4: (4, 1),
        5: (10, 1), 6: (12, 4), 7: (10, 9), 8: (7, 3),
    },
    "Sun": {
        1: (4, 12), 2: (1, 9), 3: (1, 4), 4: (4, 1),
        5: (9, 1), 6: (12, 4), 7: (12, 9), 8: (9, 12),
    },
    "Butterfly": {
        1: (6, 11), 2: (3, 9), 3: (3, 5), 4: (1, 3),
        5: (12, 3), 6: (10, 5), 7: (10, 9), 8: (6, 6),
    },
    "Bird": {
        1: (6, 12), 2: (4, 8), 3: (2, 6), 4: (1, 4),
        5: (12, 4), 6: (10, 6), 7: (8, 8), 8: (6, 9),
    },
    "Diamond": {
        1: (6, 12), 2: (3, 9), 3: (1, 6), 4: (3, 3),
        5: (6, 1), 6: (9, 3), 7: (11, 6), 8: (9, 9),
    },
}

# ----------------------------------
# ПЕСНЯ
# ----------------------------------
try:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:  # если код вставлен прямо в окно IDLE Shell
    BASE_DIR = os.getcwd()

# Папка с песней. Если перенесёшь папку, поменяй путь здесь.
SONG_FOLDER = r"C:\Users\ASUS\Desktop\Robocuo67"
SONG = os.path.join(SONG_FOLDER, "67.mp3")

# Сколько секунд играет песня. None = до конца.
SONG_SECONDS = None

# False = песня один раз, когда выполнены ВСЕ фигуры и роботы остановились.
# True  = песня после каждой фигуры.
SOUND_AFTER_EACH_FIGURE = False

SAY_PHRASE = "Ярик крутой"

# ----------------------------------
# КАК КАМЕРА ПОНИМАЕТ, ЧТО РОБОТ ОСТАНОВИЛСЯ
# ----------------------------------
STILL_SECONDS = 1.5     # столько секунд маркер не должен двигаться
STILL_PIXELS = 80       # допустимое дрожание (пиксели для кадра 640 px)
MOVE_PIXELS = 15        # на сколько сдвинуться, чтобы считалось "проехал"
REQUIRE_MOVEMENT = True  # True = без движения песню не включать
STILL_TIMEOUT = 20      # сколько секунд ждать, пока роботы остановятся

# Печать позиции и угла: каждые N секунд для каждого маркера.
# 0 = каждый кадр, None = не печатать.
PRINT_COORDS_EVERY = 0.5

# ----------------------------------
# КАМЕРА
# ----------------------------------
# USB-камера: CAMERA_INDEX (0 = встроенная, 1 = внешняя).
CAMERA_INDEX = 1
MAX_CAMERAS = 4   # сколько номеров USB перебирать (0..3)

# IP-камера Axis по RTSP. Включи USE_RTSP = True.
# ПАРОЛЬ НЕ ХРАНИ В ФАЙЛЕ: задай переменную окружения CAMERA_RTSP_URL
# (Windows: setx CAMERA_RTSP_URL "rtsp://user:pass@192.168.0.90:554/...")
USE_RTSP = False
RTSP_URL = os.environ.get(
    "CAMERA_RTSP_URL",
    "rtsp://USER:PASSWORD@192.168.0.90:554/axis-media/media.amp?camera1=1",
)
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;udp")

# Углы игрового поля на кадре, в ДОЛЯХ кадра (0..1), по часовой стрелке
# от левого верхнего. Работает для любого разрешения камеры.
# None = всё изображение целиком это поле.
FIELD_CORNERS = [
    (0.19, 0.17),   # левый верхний
    (0.84, 0.23),   # правый верхний
    (0.95, 0.875),  # правый нижний
    (0.11, 0.81),   # левый нижний
]

GRID_SIZE = 12      # сетка 12x12
MARKER_LENGTH = 0.1  # размер маркера в метрах


# ==========================================
# ЧАСТЬ 1: КАМЕРА И ARUCO (работает в фоне всё время)
# ==========================================

class CameraState:
    """Общая память между потоком камеры и программой роботов."""

    def __init__(self):
        self.lock = threading.Lock()
        self.history = {}        # id маркера -> deque[(время, x, y)]
        self.cells = {}          # id маркера -> (колонка, строка)
        self.scale = 1.0
        self.tracking = False
        self.start_pos = {}
        self.max_move = {}
        self.alive = False
        self.ready = threading.Event()
        self.stop = threading.Event()
        self.loop = None
        self.main_task = None

    def update_marker(self, marker_id, x, y, cell=None):
        now = time.monotonic()

        with self.lock:
            history = self.history.setdefault(marker_id, deque())
            history.append((now, x, y))

            if cell is not None:
                self.cells[marker_id] = cell

            while history and now - history[0][0] > 15:
                history.popleft()

            if self.tracking:
                if marker_id not in self.start_pos:
                    self.start_pos[marker_id] = (x, y)

                start_x, start_y = self.start_pos[marker_id]
                distance = math.hypot(x - start_x, y - start_y)

                if distance > self.max_move.get(marker_id, 0.0):
                    self.max_move[marker_id] = distance

    def cell_of(self, marker_id):
        """Клетка маркера, если он виден прямо сейчас, иначе None."""
        now = time.monotonic()

        with self.lock:
            history = self.history.get(marker_id)

            if not history or now - history[-1][0] > 0.5:
                return None

            return self.cells.get(marker_id)

    def start_tracking(self):
        now = time.monotonic()

        with self.lock:
            self.tracking = True
            self.start_pos = {}
            self.max_move = {}

            for marker_id, history in self.history.items():
                if history and now - history[-1][0] < 1.0:
                    self.start_pos[marker_id] = (
                        history[-1][1], history[-1][2]
                    )
                    self.max_move[marker_id] = 0.0

    def visible_ids(self):
        now = time.monotonic()

        with self.lock:
            return {
                marker_id
                for marker_id, history in self.history.items()
                if history and now - history[-1][0] <= 0.5
            }

    def markers_still(self, ids):
        """True, если все маркеры из ids видны и не двигаются STILL_SECONDS."""
        now = time.monotonic()

        with self.lock:
            threshold = STILL_PIXELS * self.scale

            for marker_id in ids:
                history = self.history.get(marker_id)

                if not history:
                    return False

                if now - history[-1][0] > 0.5:
                    return False

                window = [
                    s for s in history if now - s[0] <= STILL_SECONDS
                ]

                if len(window) < 3:
                    return False

                if window[0][0] > now - STILL_SECONDS + 0.4:
                    return False

                xs = [s[1] for s in window]
                ys = [s[2] for s in window]

                if (
                    max(xs) - min(xs) > threshold
                    or max(ys) - min(ys) > threshold
                ):
                    return False

            return True

    def markers_moved(self, ids):
        with self.lock:
            threshold = MOVE_PIXELS * self.scale

            return all(
                self.max_move.get(marker_id, 0.0) >= threshold
                for marker_id in ids
            )


state = CameraState()


def find_file(name, exts=(".mp3", ".wav", ".ogg", ".m4a", ".flac")):
    """Ищет файл name+расширение в папке песни, рядом со скриптом
    и на рабочем столе."""
    folders = [
        SONG_FOLDER,
        BASE_DIR,
        os.path.join(os.path.expanduser("~"), "Desktop", "Robocuo67"),
        os.path.join(
            os.path.expanduser("~"), "OneDrive", "Desktop", "Robocuo67"
        ),
    ]

    for folder in folders:
        for ext in exts:
            path = os.path.join(folder, name + ext)
            if os.path.exists(path):
                return path

    return None


def find_song():
    if os.path.exists(SONG):
        return SONG

    return find_file("67")


def find_pattern():
    """Возвращает название узора, если роботы стоят в нём, иначе None."""
    for name, cells in PATTERNS.items():
        if not state.markers_still(list(cells)):
            continue

        matched = True

        for marker_id, (col, row) in cells.items():
            cell = state.cell_of(marker_id)

            if (
                cell is None
                or max(abs(cell[0] - col), abs(cell[1] - row))
                > PATTERN_TOLERANCE
            ):
                matched = False
                break

        if matched:
            return name

    return None


def play_wow(name):
    if PATTERN_USE_MAIN_SONG:
        path = find_song()
    else:
        path = None

        if name in PATTERN_SOUNDS:
            path = find_file(PATTERN_SOUNDS[name])

        if path is None:
            path = find_file(WOW_SOUND)

    if path is None:
        print(f"Звук для узора «{name}» не найден (нужен {WOW_SOUND}.mp3).")
        return

    with suppress(Exception):
        playsound3.playsound(path, block=False)


def close_camera_windows():
    """Закрывает окна OpenCV (на Windows одного destroyAllWindows мало)."""
    for window_name in ("Webcam", "Grid"):
        with suppress(Exception):
            cv2.destroyWindow(window_name)
    with suppress(Exception):
        cv2.destroyAllWindows()
    for _ in range(10):
        with suppress(Exception):
            cv2.waitKey(30)


def build_sources():
    """Список источников видео: RTSP (если настроен) + USB-камеры."""
    sources = []

    if "USER:PASSWORD" not in RTSP_URL:
        sources.append(RTSP_URL)
    elif USE_RTSP:
        print(
            "RTSP не настроен: задай CAMERA_RTSP_URL или впиши адрес "
            "в RTSP_URL. Использую USB-камеру."
        )

    sources.extend(range(MAX_CAMERAS))
    return sources


def describe(source):
    # адрес RTSP содержит пароль, поэтому его не печатаем
    return "RTSP" if isinstance(source, str) else f"USB {source}"


def open_source(source):
    """Открывает камеру. RTSP через FFmpeg, USB на Windows через DirectShow."""
    if isinstance(source, str):
        capture = cv2.VideoCapture(source, cv2.CAP_FFMPEG)
        with suppress(Exception):
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return capture

    if sys.platform == "win32":
        return cv2.VideoCapture(source, cv2.CAP_DSHOW)

    return cv2.VideoCapture(source)


def read_frame_size(capture):
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))

    if width <= 0 or height <= 0:
        width, height = 640, 480

    return width, height


def make_camera_matrix(width, height):
    return np.array([
        [800, 0, width / 2],
        [0, 800, height / 2],
        [0, 0, 1]
    ], dtype=np.float32)


def make_perspective(width, height, warp_w, warp_h):
    if FIELD_CORNERS is None:
        source = np.float32([
            [0, 0], [width - 1, 0],
            [width - 1, height - 1], [0, height - 1],
        ])
    else:
        source = np.float32([
            [x * width, y * height] for x, y in FIELD_CORNERS
        ])

    destination = np.float32([
        [0, 0],
        [warp_w - 1, 0],
        [warp_w - 1, warp_h - 1],
        [0, warp_h - 1],
    ])

    return cv2.getPerspectiveTransform(source, destination)


def make_placeholder(width, height):
    image = np.zeros((height, width, 3), np.uint8)
    cv2.putText(
        image, "Waiting for camera...", (20, 40),
        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2
    )
    return image


class FrameGrabber(threading.Thread):
    """Читает кадры с камеры в отдельном потоке, чтобы окно не зависало."""

    def __init__(self, camera):
        super().__init__(name="frame-grabber", daemon=True)
        self.camera = camera
        self.running = True
        self.lock = threading.Lock()
        self.frame = None
        self.counter = 0
        self.stamp = 0.0

    def run(self):
        while self.running:
            try:
                ok, frame = self.camera.read()
            except Exception:
                ok, frame = False, None

            if ok and frame is not None:
                with self.lock:
                    self.frame = frame
                    self.counter += 1
                    self.stamp = time.monotonic()
            else:
                time.sleep(0.03)

    def latest(self):
        with self.lock:
            return self.frame, self.counter, self.stamp

    def _release(self):
        with suppress(Exception):
            self.camera.release()

    def close(self):
        self.running = False
        self.join(timeout=1.5)

        releaser = threading.Thread(target=self._release, daemon=True)
        releaser.start()
        releaser.join(timeout=3)


def run_camera():
    """Камера и её окна. Работает в ГЛАВНОМ потоке, роботы (Bluetooth)
    в другом. Камера не выключается, пока работает программа."""
    camera = None
    grabber = None

    try:
        print("--- Запуск камеры ---")

        sources = build_sources()

        if USE_RTSP and isinstance(sources[0], str):
            position = 0
        elif CAMERA_INDEX in sources:
            position = sources.index(CAMERA_INDEX)
        else:
            position = 0

        print(f"Пробую камеру: {describe(sources[position])}...")
        camera = open_source(sources[position])

        # Если выбранной камеры нет, ищем любую другую (сначала внешние)
        if not camera.isOpened():
            camera.release()
            camera = None
            print("Камера не открылась, ищу другую...")

            for candidate in reversed(range(len(sources))):
                if candidate == position:
                    continue

                trial = open_source(sources[candidate])

                if trial.isOpened():
                    camera = trial
                    position = candidate
                    print(f"Нашёл камеру: {describe(sources[position])}.")
                    break

                trial.release()

        if camera is None:
            print("Ошибка: не удалось открыть камеру!")
            return

        frame_width, frame_height = read_frame_size(camera)
        state.scale = frame_width / 640.0

        camera_matrix = make_camera_matrix(frame_width, frame_height)
        dist_coeffs = np.zeros((5, 1), dtype=np.float32)

        WARP_WIDTH = 800
        WARP_HEIGHT = 800

        perspective_matrix = make_perspective(
            frame_width, frame_height, WARP_WIDTH, WARP_HEIGHT
        )

        aruco_dict = cv2.aruco.getPredefinedDictionary(
            cv2.aruco.DICT_6X6_250
        )
        parameters = cv2.aruco.DetectorParameters()
        detector = cv2.aruco.ArucoDetector(aruco_dict, parameters)

        half = MARKER_LENGTH / 2
        object_points = np.array([
            [-half,  half, 0],
            [ half,  half, 0],
            [ half, -half, 0],
            [-half, -half, 0],
        ], dtype=np.float32)

        connected = find_file("connected")
        if connected:
            with suppress(Exception):
                playsound3.playsound(connected, block=False)

        grabber = FrameGrabber(camera)
        grabber.start()

        state.alive = True
        state.ready.set()

        print(
            f"Камера {describe(sources[position])} работает. "
            f"N — другая камера, Q или Esc — выход из камеры."
        )

        last_counter = -1
        last_print = {}
        unknown_reported = set()
        started = time.monotonic()
        stall_reported = False
        last_pattern = None

        placeholder = make_placeholder(frame_width, frame_height)
        shown = placeholder
        grid = np.zeros((WARP_HEIGHT, WARP_WIDTH, 3), np.uint8)

        while not state.stop.is_set():
            frame, counter, stamp = grabber.latest()

            # ---------- новый кадр: ищем маркеры ----------
            if frame is not None and counter != last_counter:
                last_counter = counter
                frame = frame.copy()

                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                corners, ids, rejected = detector.detectMarkers(gray)

                grid = cv2.warpPerspective(
                    frame, perspective_matrix, (WARP_WIDTH, WARP_HEIGHT)
                )

                if ids is not None:
                    cv2.aruco.drawDetectedMarkers(frame, corners, ids)

                    for marker_id, marker_corners in zip(
                        ids.flatten(), corners
                    ):
                        marker_id = int(marker_id)

                        points = marker_corners.reshape(4, 2)
                        center_x = float(points[:, 0].mean())
                        center_y = float(points[:, 1].mean())

                        # Клетка сетки (через перспективу поля)
                        center = np.array(
                            [[[center_x, center_y]]], dtype=np.float32
                        )
                        warped_x, warped_y = cv2.perspectiveTransform(
                            center, perspective_matrix
                        )[0, 0]

                        column = min(
                            max(int(warped_x * GRID_SIZE / WARP_WIDTH) + 1, 1),
                            GRID_SIZE
                        )
                        row = min(
                            max(int(warped_y * GRID_SIZE / WARP_HEIGHT) + 1, 1),
                            GRID_SIZE
                        )

                        # Запоминаем положение и клетку
                        state.update_marker(
                            marker_id, center_x, center_y, (column, row)
                        )

                        # Угол поворота робота (yaw)
                        camera_yaw = None
                        yaw_text = ""

                        try:
                            ok, rvec, tvec = cv2.solvePnP(
                                object_points,
                                points,
                                camera_matrix,
                                dist_coeffs,
                                flags=cv2.SOLVEPNP_IPPE_SQUARE,
                            )

                            if ok:
                                cv2.drawFrameAxes(
                                    frame, camera_matrix, dist_coeffs,
                                    rvec, tvec, 0.05
                                )

                                rotation_matrix, _ = cv2.Rodrigues(rvec)
                                yaw_degrees = np.degrees(
                                    np.arctan2(
                                        rotation_matrix[1, 0],
                                        rotation_matrix[0, 0]
                                    )
                                )
                                camera_yaw = float(-yaw_degrees)
                                yaw_text = f" {round(camera_yaw)}deg"
                        except cv2.error:
                            pass

                        known = marker_id in ROBOTS
                        robot_name = ROBOTS.get(
                            marker_id, f"Marker {marker_id} (not in ROBOTS)"
                        )

                        if not known and marker_id not in unknown_reported:
                            unknown_reported.add(marker_id)
                            print(
                                f"Вижу маркер №{marker_id}, его нет в списке "
                                f"ROBOTS. Если он на роботе, впиши номер "
                                f"{marker_id} в ROBOTS в начале файла."
                            )

                        if PRINT_COORDS_EVERY is not None:
                            now = time.monotonic()

                            if (
                                now - last_print.get(marker_id, -1e9)
                                >= PRINT_COORDS_EVERY
                            ):
                                last_print[marker_id] = now
                                angle = (
                                    round(camera_yaw, 1)
                                    if camera_yaw is not None else "?"
                                )
                                print(
                                    robot_name, "позиция:", column, row,
                                    "угол:", angle
                                )

                        cv2.putText(
                            frame,
                            f"{robot_name} [{column},{row}]{yaw_text}",
                            (int(center_x), max(20, int(center_y) - 15)),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.5,
                            (0, 255, 0),
                            2
                        )

                # Сетка 12x12
                for i in range(1, GRID_SIZE):
                    x = WARP_WIDTH * i // GRID_SIZE
                    y = WARP_HEIGHT * i // GRID_SIZE
                    cv2.line(grid, (x, 0), (x, WARP_HEIGHT), (0, 0, 255), 1)
                    cv2.line(grid, (0, y), (WARP_WIDTH, y), (0, 0, 255), 1)

                # Статус: стоят маркеры или двигаются
                if state.markers_still(list(ROBOTS)):
                    status, color = "STILL", (0, 255, 0)
                elif state.visible_ids() & set(ROBOTS):
                    status, color = "MOVING", (0, 200, 255)
                else:
                    status, color = "NO MARKER", (0, 0, 255)

                cv2.putText(
                    frame,
                    f"{describe(sources[position])} | {status} | "
                    f"N - next camera",
                    (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    color,
                    2
                )

                # Узоры: роботы выстроились в фигуру?
                if PATTERNS_ENABLED:
                    found = find_pattern()

                    if found:
                        cv2.putText(
                            frame, f"Figure: {found}", (10, 85),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                            (255, 255, 0), 2
                        )

                    if found and found != last_pattern:
                        print(f"*** Узор «{found}» собран! ***")
                        play_wow(found)

                    last_pattern = found

                shown = frame

            # ---------- камера перестала отдавать кадры? ----------
            now = time.monotonic()
            last_frame_time = stamp if stamp else started
            frame_age = now - last_frame_time

            display = shown

            if frame_age > 3:
                display = shown.copy()
                cv2.putText(
                    display,
                    f"NO FRAMES for {int(frame_age)} s - camera stalled?",
                    (10, 55),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 0, 255),
                    2
                )

                if not stall_reported:
                    stall_reported = True
                    print(
                        "Камера не отдаёт кадры. Проверь кабель/сеть "
                        "или нажми N, чтобы выбрать другую камеру."
                    )

            else:
                stall_reported = False

            # Если кадров нет больше 5 секунд, песня включится без
            # проверки камерой (чтобы не сорвать показ).
            state.alive = frame_age <= 5

            cv2.imshow("Webcam", display)
            cv2.imshow("Grid", grid)

            key = cv2.waitKey(10) & 0xFF

            if key in (ord("q"), ord("Q"), 27):
                print("Камера закрыта по клавише.")
                break

            if key in (ord("n"), ord("N")):
                grabber.close()
                switched = False

                for step in range(1, len(sources) + 1):
                    candidate = (position + step) % len(sources)
                    new_camera = open_source(sources[candidate])

                    if new_camera.isOpened():
                        camera = new_camera
                        position = candidate
                        switched = True
                        break

                    new_camera.release()

                if not switched:
                    print("Другой камеры не найдено, возвращаю прежнюю.")
                    camera = open_source(sources[position])

                grabber = FrameGrabber(camera)
                grabber.start()

                last_counter = -1
                started = time.monotonic()
                last_pattern = None

                frame_width, frame_height = read_frame_size(camera)
                state.scale = frame_width / 640.0
                camera_matrix = make_camera_matrix(
                    frame_width, frame_height
                )
                perspective_matrix = make_perspective(
                    frame_width, frame_height, WARP_WIDTH, WARP_HEIGHT
                )
                placeholder = make_placeholder(frame_width, frame_height)
                shown = placeholder

                if switched:
                    print(f"Переключился на {describe(sources[position])}.")

                continue

            # Если окно закрыли крестиком, камера останавливается
            try:
                if (
                    cv2.getWindowProperty(
                        "Webcam", cv2.WND_PROP_VISIBLE
                    ) < 1
                    or cv2.getWindowProperty(
                        "Grid", cv2.WND_PROP_VISIBLE
                    ) < 1
                ):
                    print(
                        "Окно камеры закрыто, камера остановлена. "
                        "Песня по камере работать не будет."
                    )
                    break
            except cv2.error:
                break

    except Exception as e:
        print(f"Ошибка камеры: {type(e).__name__}: {e}")

    finally:
        state.alive = False
        state.ready.set()

        if grabber is not None:
            grabber.close()
        elif camera is not None:
            with suppress(Exception):
                camera.release()

        close_camera_windows()


# ==========================================
# ЧАСТЬ 2: ROBOTS + BLE
# ==========================================

PYBRICKS_COMMAND_EVENT_CHAR_UUID = (
    "c5f50002-8280-46da-89f4-6d8051e4aeef"
)


def beep_melody():
    """Запасная мелодия, если файла песни нет (только Windows)."""
    try:
        import winsound
    except ImportError:
        return

    for freq, ms in (
        (523, 200), (659, 200), (784, 200),
        (1047, 400), (784, 200), (1047, 600),
    ):
        winsound.Beep(freq, ms)


def speak_phrase(text):
    """Говорит фразу голосом Windows. Нужен русский голос в Windows."""
    if sys.platform != "win32":
        print("Голос работает только на Windows.")
        return

    import subprocess

    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "try { $s.SelectVoiceByHints('NotSet', 'NotSet', 0, "
        "[System.Globalization.CultureInfo]'ru-RU') } catch {}; "
        f"$s.Speak('{text}')"
    )

    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            creationflags=0x08000000,  # без чёрного окна
            timeout=20,
        )
    except Exception as e:
        print(f"Не удалось сказать фразу: {e}")


async def play_song():
    """Включает песню и ждёт конца (или SONG_SECONDS)."""
    song_path = find_song()

    if song_path is None:
        print(f"Файл песни не найден. Положи 67.mp3 в папку: {SONG_FOLDER}")
        print("Пока играет запасная мелодия...")
        await asyncio.to_thread(beep_melody)
        return

    try:
        sound = playsound3.playsound(song_path, block=False)
    except Exception as e:
        print(f"Не удалось включить песню: {e}")
        return

    if SONG_SECONDS is None:
        await asyncio.to_thread(sound.wait)
    else:
        await asyncio.sleep(SONG_SECONDS)
        with suppress(Exception):
            sound.stop()


def check_figures():
    """Проверяет, что в каждом шаге каждой фигуры по числу на каждый хаб."""
    problems = []

    for number, steps in FIGURES.items():
        for step_number, step in enumerate(steps, 1):
            if len(step) != len(HUB_NAMES):
                problems.append(
                    f"Фигура {number}, шаг {step_number}: "
                    f"{len(step)} знач., а хабов {len(HUB_NAMES)}"
                )

    return problems


async def ask_input(prompt):
    """Читает строку из консоли, не блокируя Bluetooth."""
    loop = asyncio.get_running_loop()
    future = loop.create_future()

    def deliver(setter, value):
        if not future.done():
            setter(value)

    def reader():
        try:
            text = input(prompt)
        except BaseException as e:
            with suppress(RuntimeError):
                loop.call_soon_threadsafe(deliver, future.set_exception, e)
        else:
            with suppress(RuntimeError):
                loop.call_soon_threadsafe(deliver, future.set_result, text)

    threading.Thread(target=reader, name="input", daemon=True).start()
    return await future


async def main():
    main_task = asyncio.current_task()
    state.loop = asyncio.get_running_loop()
    state.main_task = main_task

    problems = check_figures()

    if problems:
        print("Ошибка в FIGURES (проверь настройки в начале файла):")
        for problem in problems:
            print("  -", problem)
        return

    ready_events = [asyncio.Event() for _ in HUB_NAMES]
    clients = []

    # Сообщения «err...» от хабов за текущий шаг: (номер хаба, текст)
    hub_errors = []

    def create_rx_handler(index):
        """Разбор сообщений хаба.

        Bluetooth режет длинные сообщения на куски и может склеивать конец
        одного с началом следующего, поэтому сообщения копятся в буфере,
        а «rdy» ищется внутри буфера."""
        buffer = bytearray()
        flush_handle = [None]

        def show(raw):
            text = bytes(raw).decode(errors="ignore").strip()

            if not text:
                return

            print(f"Хаб {HUB_NAMES[index]} пишет: {text}")

            if text.lower().startswith("err"):
                hub_errors.append((index, text))

        def flush():
            flush_handle[0] = None

            if buffer:
                show(buffer)
                buffer.clear()

        def handle_rx(_, data: bytearray):
            if not data or data[0] != 0x01:
                return

            buffer.extend(data[1:])

            got_ready = False

            while True:
                pos = buffer.find(b"rdy")

                if pos < 0:
                    break

                del buffer[pos:pos + 3]
                got_ready = True

            while True:
                newline = buffer.find(b"\n")

                if newline < 0:
                    break

                line = bytes(buffer[:newline])
                del buffer[:newline + 1]
                show(line)

            if flush_handle[0] is not None:
                flush_handle[0].cancel()
                flush_handle[0] = None

            if buffer and state.loop is not None:
                flush_handle[0] = state.loop.call_later(0.4, flush)

            if got_ready:
                print(f"--- Хаб {HUB_NAMES[index]} ГОТОВ ---")
                ready_events[index].set()

        return handle_rx

    # Когда True — мы сами закрываем соединения
    shutting_down = False

    # Bluetooth-адрес -> номер хаба в HUB_NAMES
    address_to_index = {}

    # Номера хабов, с которыми потеряна связь
    lost_hubs = set()

    def handle_disconnect(client):
        if shutting_down:
            return

        index = address_to_index.get(client.address)

        if index is None:
            print(f"!!! Отключился неизвестный хаб {client.address}.")
            if not main_task.done():
                main_task.cancel()
            return

        if index < len(clients) and clients[index] is not client:
            return

        print(
            f"!!! Хаб {HUB_NAMES[index]} отключился ({client.address}). "
            f"Проверь, что он включён и заряжен."
        )
        lost_hubs.add(index)

    async def wait_ready(timeout):
        """Ждёт rdy от всех хабов. Если хаб потерян — сразу ошибка."""
        loop = asyncio.get_running_loop()
        waiter = asyncio.ensure_future(
            asyncio.gather(*(event.wait() for event in ready_events))
        )
        deadline = loop.time() + timeout

        try:
            while not waiter.done():
                if lost_hubs:
                    names = ", ".join(
                        HUB_NAMES[i] for i in sorted(lost_hubs)
                    )
                    raise ConnectionError(
                        f"потеряна связь с хабом {names}"
                    )

                if loop.time() > deadline:
                    raise asyncio.TimeoutError

                await asyncio.sleep(0.1)
        finally:
            if not waiter.done():
                waiter.cancel()

            def _retrieve(f):
                with suppress(BaseException):
                    f.exception()

            waiter.add_done_callback(_retrieve)

    async def reconnect_lost_hubs():
        """Переподключает потерянные хабы. True, если все хабы в строю."""
        for i, client in enumerate(clients):
            if not client.is_connected:
                lost_hubs.add(i)

        for i in sorted(lost_hubs):
            name = HUB_NAMES[i]
            print(f"Переподключаю хаб {name}...")

            with suppress(Exception):
                await asyncio.wait_for(clients[i].disconnect(), timeout=5)

            device = await BleakScanner.find_device_by_name(
                name, timeout=10
            )

            if device is None:
                print(
                    f"Хаб {name} не найден. Включи его и введи "
                    f"команду ещё раз."
                )
                return False

            address_to_index[device.address] = i

            new_client = BleakClient(
                device,
                disconnected_callback=handle_disconnect,
                timeout=15.0
            )

            try:
                await asyncio.wait_for(new_client.connect(), timeout=20)
                await new_client.start_notify(
                    PYBRICKS_COMMAND_EVENT_CHAR_UUID,
                    create_rx_handler(i)
                )

                # Перезапускаем программу на хабе, чтобы он снова прислал rdy
                ready_events[i].clear()

                with suppress(Exception):
                    await new_client.write_gatt_char(
                        PYBRICKS_COMMAND_EVENT_CHAR_UUID,
                        b"\x00",
                        response=True
                    )
                    await asyncio.sleep(0.5)

                await new_client.write_gatt_char(
                    PYBRICKS_COMMAND_EVENT_CHAR_UUID,
                    b"\x01",
                    response=True
                )

                await asyncio.wait_for(
                    ready_events[i].wait(), timeout=15
                )
            except Exception as e:
                print(
                    f"Не удалось вернуть хаб {name}: "
                    f"{type(e).__name__}: {e}"
                )
                with suppress(Exception):
                    await new_client.disconnect()
                return False

            clients[i] = new_client
            lost_hubs.discard(i)
            print(f"Хаб {name} снова в строю.")

        return True

    async def send_all(data_list):
        if len(data_list) != len(clients):
            raise ValueError(
                f"В шаге {len(data_list)} значений, а хабов "
                f"{len(clients)}. Проверь FIGURES."
            )

        await wait_ready(30)

        for event in ready_events:
            event.clear()

        tasks = []

        hub_errors.clear()

        for i, client in enumerate(clients):
            payload = b"\x06" + data_list[i] + COMMAND_END

            tasks.append(
                client.write_gatt_char(
                    PYBRICKS_COMMAND_EVENT_CHAR_UUID,
                    payload,
                    response=True
                )
            )

        await asyncio.gather(*tasks)

        await wait_ready(60)

        for hub_index, text in hub_errors:
            print(
                f"!!! Хаб {HUB_NAMES[hub_index]} не понял команду "
                f"{data_list[hub_index].decode(errors='ignore')} "
                f"(ответ: «{text}»). Робот, скорее всего, не поехал. "
                f"Проверь программу на хабе или попробуй другое значение "
                f"COMMAND_END в начале файла."
            )

        hub_errors.clear()

    async def celebrate():
        """Ждёт, пока камера увидит, что маркеры стоят, и включает песню."""
        if not state.alive:
            print("Камера не работает — включаю песню без проверки.")
            await play_song()
            return

        ids = list(ROBOTS)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + STILL_TIMEOUT

        print("Жду, пока камера увидит, что роботы остановились...")

        while not state.markers_still(ids):
            if not state.alive:
                print("Камера остановилась — включаю песню без проверки.")
                await play_song()
                return

            if loop.time() > deadline:
                seen = state.visible_ids()
                missing = [ROBOTS[i] for i in ids if i not in seen]

                if missing:
                    print(
                        f"Камера не видит маркер: {', '.join(missing)}. "
                        f"Песню не включаю."
                    )
                else:
                    print("Роботы всё ещё двигаются. Песню не включаю.")

                return

            await asyncio.sleep(0.1)

        if REQUIRE_MOVEMENT and not state.markers_moved(ids):
            print(
                "Камера не заметила, что робот ехал (координаты не "
                "менялись). Песню не включаю."
            )
            return

        print("Ооооо, ты проехал вперёд! Какой Ярик молодец!")
        await asyncio.to_thread(speak_phrase, SAY_PHRASE)
        await play_song()

    async def run_figures(numbers):
        """Выполняет фигуры по очереди, шаг за шагом."""
        if not SOUND_AFTER_EACH_FIGURE:
            state.start_tracking()

        for number in numbers:
            steps = FIGURES[number]

            if SOUND_AFTER_EACH_FIGURE:
                state.start_tracking()

            print(f"\n=== Фигура {number} ===")

            for step_number, step in enumerate(steps, 1):
                print(f"Фигура {number}, шаг {step_number} из {len(steps)}...")
                await send_all(step)

            print(f"Фигура {number} выполнена.")

            if SOUND_AFTER_EACH_FIGURE:
                await celebrate()

        if not SOUND_AFTER_EACH_FIGURE:
            await celebrate()

        print("Готово.")

    try:
        # ----------------------------------
        # ПОИСК ХАБОВ
        # ----------------------------------

        print("--- Поиск Bluetooth-хабов ---")

        devices = []

        for name in HUB_NAMES:
            print(f"Поиск хаба {name}...")

            device = await BleakScanner.find_device_by_name(
                name, timeout=10
            )

            if device is None:
                print(f"Ошибка: хаб {name} не найден!")
                return

            devices.append(device)
            address_to_index[device.address] = len(devices) - 1
            print(f"Найден хаб: {name}")

        # ----------------------------------
        # ПОДКЛЮЧЕНИЕ
        # ----------------------------------

        print("\n--- Подключение к хабам ---")

        for i, device in enumerate(devices):
            name = HUB_NAMES[i]

            print(f"Подключаемся к хабу {name}...")

            client = BleakClient(
                device,
                disconnected_callback=handle_disconnect,
                timeout=15.0
            )

            try:
                await asyncio.wait_for(client.connect(), timeout=20)
            except Exception as e:
                print(f"Ошибка подключения к хабу {name}: {e}")

                with suppress(Exception):
                    await client.disconnect()

                continue

            if not client.is_connected:
                print(f"Хаб {name} не подключён.")
                continue

            clients.append(client)
            print(f"Bluetooth подключён: {name}")

            try:
                await client.start_notify(
                    PYBRICKS_COMMAND_EVENT_CHAR_UUID,
                    create_rx_handler(i)
                )
            except Exception as e:
                print(f"Ошибка уведомлений хаба {name}: {e}")
                break

            print(f"Уведомления включены: {name}")
            await asyncio.sleep(1)

        if (
            len(clients) != len(HUB_NAMES)
            or any(not client.is_connected for client in clients)
        ):
            print(
                "\nНе все хабы подключились. "
                "Команды роботам не отправляются."
            )
            return

        # ----------------------------------
        # ЗАПУСК ПРОГРАММ НА РОБОТАХ
        # ----------------------------------

        print("\nЗапуск программ на роботах...")

        for client in clients:
            await client.write_gatt_char(
                PYBRICKS_COMMAND_EVENT_CHAR_UUID,
                b"\x01",
                response=True
            )

        print("Ожидание сигнала rdy от всех хабов...")

        await asyncio.wait_for(
            asyncio.gather(*(event.wait() for event in ready_events)),
            timeout=30
        )

        print("Все системы в норме!")

        # ----------------------------------
        # КОМАНДЫ
        # ----------------------------------

        stop_words = ("стоп", "stop")
        go_words = ("вперед", "вперёд", "vpered", "go")

        while True:
            command = await ask_input(
                "\nКоманда (вперед = все фигуры, 1 / 2 ... = одна фигура, "
                "стоп): "
            )

            command = command.strip().lower()

            if any(w in command for w in stop_words):
                print("Отправка команды остановки...")

                for client in clients:
                    with suppress(Exception):
                        await client.write_gatt_char(
                            PYBRICKS_COMMAND_EVENT_CHAR_UUID,
                            b"\x06stop\r\n",
                            response=True
                        )

                print("Команда остановки отправлена.")
                break

            if any(w in command for w in go_words):
                numbers = sorted(FIGURES)
            else:
                match = re.fullmatch(
                    r"(?:фигура|figure|fig)?\s*(\d+)", command
                )

                if not match:
                    print("Неизвестная команда.")
                    continue

                number = int(match.group(1))

                if number not in FIGURES:
                    print(
                        f"Фигуры {number} нет. "
                        f"Есть фигуры: {sorted(FIGURES)}."
                    )
                    continue

                numbers = [number]

            # Если какой-то хаб отключился — сначала возвращаем его
            if not await reconnect_lost_hubs():
                continue

            print("Запуск программы...")

            try:
                await run_figures(numbers)

            except asyncio.TimeoutError:
                print(
                    "Истекло время ожидания ответа. "
                    "Проверь программы на хабах."
                )

            except ConnectionError as e:
                print(
                    f"Остановлено: {e}. Включи хаб и введи команду "
                    f"ещё раз — я его переподключу."
                )

            except Exception as e:
                print(
                    f"Ошибка связи с хабом: {type(e).__name__}: {e}. "
                    f"Введи команду ещё раз — я проверю соединения."
                )

    except asyncio.CancelledError:
        print("Bluetooth-соединение прервано.")

    except asyncio.TimeoutError:
        print("Истекло время ожидания ответа от хабов.")

    except Exception as e:
        print(f"Критическая ошибка: {type(e).__name__}: {e}")

    finally:
        shutting_down = True
        print("Закрытие соединений...")

        for client in clients:
            try:
                if client.is_connected:
                    with suppress(Exception):
                        await asyncio.wait_for(
                            client.stop_notify(
                                PYBRICKS_COMMAND_EVENT_CHAR_UUID
                            ),
                            timeout=5
                        )
                    await asyncio.wait_for(
                        client.disconnect(), timeout=10
                    )
            except (Exception, asyncio.CancelledError) as e:
                print(
                    f"Не удалось отключить хаб {client.address}: "
                    f"{type(e).__name__}"
                )

        await asyncio.sleep(1)

        print("Работа завершена.")


def run_robots():
    """Роботы (Bluetooth) работают в отдельном потоке. Когда они закончили
    (команда «стоп»), камера тоже выключается."""
    try:
        # Роботы подключаются сразу, не дожидаясь камеры:
        # камера и Bluetooth стартуют одновременно.
        print("\n--- Запуск роботов (камера работает параллельно) ---\n")

        with suppress(asyncio.CancelledError):
            asyncio.run(main())

    except Exception as e:
        print(f"Ошибка в части роботов: {type(e).__name__}: {e}")

    finally:
        state.stop.set()


if __name__ == "__main__":
    robots_thread = threading.Thread(target=run_robots, name="robots")
    robots_thread.start()

    try:
        run_camera()

        # Камера закончила, а роботы ещё работают: ждём команду «стоп»
        while robots_thread.is_alive():
            robots_thread.join(timeout=0.5)

    except KeyboardInterrupt:
        print("\nПрервано с клавиатуры. Отключаю роботов...")
        state.stop.set()

        loop, task = state.loop, state.main_task

        if loop is not None and task is not None:
            with suppress(Exception):
                loop.call_soon_threadsafe(task.cancel)

        robots_thread.join(timeout=15)

    finally:
        state.stop.set()
        print("Камера выключена.")
