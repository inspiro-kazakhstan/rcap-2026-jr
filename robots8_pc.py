# ==========================================
# 8 РОБОТОВ: КАМЕРА ВИДИТ СТАРТ, ФИГУРА ЗАДАЁТ ФИНИШ.
# КАЖДОМУ ХАБУ УХОДЯТ СТАРТ И ФИНИШ ВСЕХ 8 РОБОТОВ,
# PYBRICKS САМ СТРОИТ БЕЗОПАСНЫЙ МАРШРУТ.
# ПОСЛЕ КАЖДОЙ ФИГУРЫ ИГРАЕТ МУЗЫКА.
# ==========================================
import sys
sys.coinit_flags = 0

try:
    from bleak.backends.winrt.util import allow_sta
    allow_sta()
except ImportError:
    pass

import asyncio
import json
import math
import os
import re
import threading
import time
from contextlib import suppress

import cv2
import numpy as np
import playsound3
from bleak import BleakClient, BleakScanner

# ==========================================
# НАСТРОЙКИ
# ==========================================
CAMERA_INDEX = 1
MAX_CAMERAS = 4
ARUCO_DICT = cv2.aruco.DICT_6X6_250

MARKER_MM = 100.0        # сторона маркера в миллиметрах (для масштаба)
HEADING_OFFSET = 0.0     # если «перед» робота не совпадает с верхом маркера:
                         # поставь 90, 180 или -90

# {номер маркера: Bluetooth-имя хаба}. Впиши свои 8 штук.
ROBOTS = {
    1: "1",
    2: "2",
    3: "inspiro 2",
    4: "3",
    5: "4",
    6: "5",
    7: "6",
    8: "7",
}

# Фигуры: {номер фигуры: {номер маркера: (x, y) конечной точки в пикселях кадра}}
# Роботы, которых в фигуре нет, остаются на месте (но другие их объезжают).
FIGURES = {
    1: {1: (330, 164), 3: (418, 316), 6: (182, 273)},
}
FIGURES_FILE = "figures.json"   # сюда пишет команда «save N»

# Музыка (как в твоём первом скрипте)
SONG = r"C:\Users\ASUS\Desktop\Robocuo67\67.mp3"
SONG_SECONDS = None      # None = играть до конца

ARRIVE_PX = 25           # ближе этого к цели = приехал
MAX_ROUNDS = 2           # сколько раз подправлять, если кто-то не доехал
SETTLE_SEC = 1.5         # пауза, чтобы камера увидела, где роботы остановились
PLAN_TIMEOUT = 30        # сколько ждать, пока хабы примут план
DRIVE_TIMEOUT = 240      # сколько ждать, пока хабы доедут

UART = "c5f50002-8280-46da-89f4-6d8051e4aeef"
CHUNK = 19               # Bluetooth пропускает ~20 байт за раз, команды режем

# ==========================================
# ОБЩАЯ ПАМЯТЬ КАМЕРЫ
# ==========================================
positions = {}            # маркер -> {x, y, heading, mmpp, t}
pos_lock = threading.Lock()
stop_event = threading.Event()
current_targets = {}      # для рисования целей в окне камеры


def snapshot():
    """Маркеры, которые камера видит прямо сейчас."""
    now = time.monotonic()
    with pos_lock:
        return {i: dict(p) for i, p in positions.items() if now - p["t"] < 0.5}


def load_figures():
    if not os.path.exists(FIGURES_FILE):
        return
    with suppress(Exception):
        with open(FIGURES_FILE, encoding="utf-8") as f:
            data = json.load(f)
        for number, cells in data.items():
            FIGURES[int(number)] = {int(m): tuple(xy) for m, xy in cells.items()}
        print(f"Фигуры загружены из {FIGURES_FILE}: {sorted(FIGURES)}")


def save_figures():
    data = {str(n): {str(m): list(xy) for m, xy in c.items()} for n, c in FIGURES.items()}
    with open(FIGURES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


# ==========================================
# ЧАСТЬ 1: КАМЕРА (главный поток)
# ==========================================
def open_camera(index):
    if sys.platform == "win32":
        return cv2.VideoCapture(index, cv2.CAP_DSHOW)
    return cv2.VideoCapture(index)


def run_camera():
    camera = open_camera(CAMERA_INDEX)

    if not camera.isOpened():
        camera.release()
        camera = None
        for i in range(MAX_CAMERAS):
            trial = open_camera(i)
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
    print("Камера работает. Q или Esc закрывают окно камеры.")

    try:
        while not stop_event.is_set():
            ok, frame = camera.read()

            if not ok or frame is None:
                time.sleep(0.03)
                if cv2.waitKey(1) & 0xFF in (27, ord("q"), ord("Q")):
                    break
                continue

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            corners, ids, _ = detector.detectMarkers(gray)

            if ids is not None:
                cv2.aruco.drawDetectedMarkers(frame, corners, ids)

                for marker_id, c in zip(ids.flatten(), corners):
                    p = c.reshape(4, 2)
                    center = p.mean(axis=0)
                    top = (p[0] + p[1]) / 2          # середина верхней стороны

                    # «Куда смотрит» робот: от центра к верху маркера.
                    # Угол в координатах картинки (y вниз): + это по часовой.
                    heading = math.degrees(
                        math.atan2(top[1] - center[1], top[0] - center[0])
                    ) + HEADING_OFFSET

                    side = np.mean([
                        np.linalg.norm(p[(k + 1) % 4] - p[k]) for k in range(4)
                    ])

                    with pos_lock:
                        positions[int(marker_id)] = {
                            "x": float(center[0]),
                            "y": float(center[1]),
                            "heading": heading,
                            "mmpp": MARKER_MM / float(side),   # мм в одном пикселе
                            "t": time.monotonic(),
                        }

                    cv2.putText(
                        frame, f"{int(marker_id)} {round(heading)}deg",
                        (int(center[0]), max(20, int(center[1]) - 15)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2,
                    )

            # Цели текущей фигуры: красные кружки
            for marker_id, (ex, ey) in dict(current_targets).items():
                cv2.circle(frame, (int(ex), int(ey)), 12, (0, 0, 255), 2)
                cv2.putText(
                    frame, str(marker_id), (int(ex) + 14, int(ey)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2,
                )

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


# ==========================================
# ЧАСТЬ 2: BLUETOOTH И ПЛАНЫ
# ==========================================
class Hub:
    def __init__(self, marker, name):
        self.marker = marker
        self.name = name
        self.client = None
        self.ready = asyncio.Event()
        self.error = False
        self.text = ""

    def on_data(self, _, data):
        if not data or data[0] != 0x01:
            return

        self.text += bytes(data[1:]).decode(errors="ignore")

        while "rdy" in self.text:
            self.text = self.text.replace("rdy", "", 1)
            self.ready.set()

        while "\n" in self.text:
            line, self.text = self.text.split("\n", 1)
            line = line.strip()
            if line:
                print(f"Хаб {self.name}: {line}")
                if line.startswith("err"):
                    self.error = True

    async def connect(self):
        device = await BleakScanner.find_device_by_name(self.name, timeout=10)

        if device is None:
            raise RuntimeError(f"хаб {self.name} не найден")

        self.client = BleakClient(device, timeout=15.0)
        await self.client.connect()
        await self.client.start_notify(UART, self.on_data)
        await self.client.write_gatt_char(UART, b"\x01", response=True)  # старт программы
        await asyncio.wait_for(self.ready.wait(), 20)

    async def send(self, text):
        """Отправка строки. Длинные строки режутся на куски по CHUNK байт."""
        self.ready.clear()
        self.error = False
        data = text.encode() + b"\r\n"

        for i in range(0, len(data), CHUNK):
            await self.client.write_gatt_char(
                UART, b"\x06" + data[i:i + CHUNK], response=True
            )


async def wait_all(group, timeout):
    await asyncio.wait_for(
        asyncio.gather(*(h.ready.wait() for h in group)), timeout
    )


def not_arrived(targets):
    seen = snapshot()
    return [
        m for m, (ex, ey) in targets.items()
        if m in seen and math.hypot(ex - seen[m]["x"], ey - seen[m]["y"]) > ARRIVE_PX
    ]


async def run_figure(hubs, targets):
    """Одна фигура: камера читает старты, хабам уходят старты и финиши
    всех роботов, хабы сами едут без столкновений."""
    for round_number in range(1, MAX_ROUNDS + 1):
        seen = snapshot()
        members = [m for m in sorted(ROBOTS) if m in hubs and m in seen]
        lost = [m for m in ROBOTS if m not in seen]

        if lost:
            print(f"Камера не видит маркеры {lost}. Эти роботы не едут, "
                  f"и их не объедут!")

        moving = {
            m for m in members
            if m in targets
            and math.hypot(targets[m][0] - seen[m]["x"],
                           targets[m][1] - seen[m]["y"]) > ARRIVE_PX
        }

        if not moving:
            print("Все роботы на своих местах.")
            return True

        print(f"Заезд {round_number}: нужно ехать роботам {sorted(moving)}")

        mmpp = sorted(seen[m]["mmpp"] for m in members)[len(members) // 2]
        rows = []

        for m in members:
            p = seen[m]
            ex, ey = targets[m] if m in moving else (p["x"], p["y"])
            rows.append(
                f"{m} {p['x']:.0f} {p['y']:.0f} {p['heading']:.0f} "
                f"{ex:.0f} {ey:.0f}"
            )

        group = [hubs[m] for m in members]

        # 1) каждому хабу весь план: старт и финиш всех роботов (с номерами маркеров)
        plan = f"plan {len(members)} {mmpp:.4f} " + " ".join(rows)
        await asyncio.gather(*(hub.send(plan) for hub in group))
        await wait_all(group, PLAN_TIMEOUT)

        if any(h.error for h in group):
            print("Хаб не принял план. Фигура остановлена.")
            return False

        # 2) все хабы стартуют одновременно
        await asyncio.gather(*(h.send("start") for h in group))
        await wait_all(group, DRIVE_TIMEOUT)

        await asyncio.sleep(SETTLE_SEC)

    bad = not_arrived(targets)

    if bad:
        print(f"Не доехали роботы {bad}. Проверь HEADING_OFFSET и размеры колёс.")
        return False

    return True


async def play_song():
    """Включает песню и ждёт конца (или SONG_SECONDS)."""
    if not os.path.exists(SONG):
        print(f"Файл песни не найден: {SONG}")
        return

    try:
        sound = playsound3.playsound(SONG, block=False)
    except Exception as e:
        print(f"Не удалось включить песню: {e}")
        return

    if SONG_SECONDS is None:
        await asyncio.to_thread(sound.wait)
    else:
        await asyncio.sleep(SONG_SECONDS)
        with suppress(Exception):
            sound.stop()


async def run_figures(hubs, numbers):
    """Фигура -> музыка -> следующая фигура -> музыка -> ..."""
    global current_targets

    for number in numbers:
        print(f"\n=== Фигура {number} ===")
        current_targets = FIGURES[number]

        try:
            done = await run_figure(hubs, current_targets)
        finally:
            current_targets = {}

        print(f"Фигура {number} {'выполнена' if done else 'выполнена не полностью'}.")
        print("Музыка!")
        await play_song()

    print("Готово.")


async def ask_input(prompt):
    loop = asyncio.get_running_loop()
    future = loop.create_future()

    def reader():
        try:
            text = input(prompt)
        except BaseException as e:
            with suppress(RuntimeError):
                loop.call_soon_threadsafe(
                    lambda: future.done() or future.set_exception(e))
        else:
            with suppress(RuntimeError):
                loop.call_soon_threadsafe(
                    lambda: future.done() or future.set_result(text))

    threading.Thread(target=reader, daemon=True).start()
    return await future


async def main():
    hubs = {}

    try:
        for marker, name in ROBOTS.items():
            print(f"Подключаю хаб {name} (маркер {marker})...")
            hub = Hub(marker, name)
            await hub.connect()
            hubs[marker] = hub
            print(f"Хаб {name} готов.")

        print("\nВсе хабы готовы.")

        while True:
            cmd = (await ask_input(
                "\nКоманда: вперед = все фигуры по порядку, N = одна фигура, "
                "save N = запомнить текущие места как фигуру N, list, стоп: "
            )).strip().lower()

            if cmd in ("стоп", "stop"):
                for hub in hubs.values():
                    with suppress(Exception):
                        await hub.send("stop")
                break

            if cmd == "list":
                for n, cells in sorted(FIGURES.items()):
                    print(f"Фигура {n}: {cells}")
                continue

            m = re.fullmatch(r"save\s+(\d+)", cmd)
            if m:
                number = int(m.group(1))
                seen = snapshot()
                FIGURES[number] = {
                    i: (round(p["x"]), round(p["y"]))
                    for i, p in seen.items() if i in ROBOTS
                }
                save_figures()
                print(f"Фигура {number} записана: {FIGURES[number]}")
                continue

            if cmd in ("вперед", "вперёд", "go"):
                numbers = sorted(FIGURES)
            else:
                m = re.fullmatch(r"(?:фигура|figure|fig)?\s*(\d+)", cmd)
                if not m or int(m.group(1)) not in FIGURES:
                    print(f"Не понял. Есть фигуры: {sorted(FIGURES)}")
                    continue
                numbers = [int(m.group(1))]

            try:
                await run_figures(hubs, numbers)
            except asyncio.TimeoutError:
                print("Хабы не ответили вовремя. Проверь программы на хабах.")
            except Exception as e:
                print(f"Ошибка: {type(e).__name__}: {e}")

    except Exception as e:
        print(f"Критическая ошибка: {type(e).__name__}: {e}")

    finally:
        for hub in hubs.values():
            if hub.client is not None:
                with suppress(Exception):
                    await asyncio.wait_for(hub.client.disconnect(), 10)
        print("Хабы отключены.")


def run_robots():
    try:
        asyncio.run(main())
    finally:
        stop_event.set()


if __name__ == "__main__":
    load_figures()
    robots_thread = threading.Thread(target=run_robots, name="robots")
    robots_thread.start()

    try:
        run_camera()

        while robots_thread.is_alive():
            robots_thread.join(timeout=0.5)
    except KeyboardInterrupt:
        stop_event.set()
