import json
import queue

import sounddevice as sd
from vosk import Model, KaldiRecognizer

import asyncio
import threading
from contextlib import suppress

import playsound3
from bleak import BleakClient, BleakScanner

UART = "c5f50002-8280-46da-89f4-6d8051e4aeef"
CHUNK = 19
SEND_EVERY = 0.01
CONNECTED_PATH = "C:/Users/tolik/Documents/GitHub/rcap-2026-jr/audio/connected.mp3"

MODEL_PATH = r"C:\Users\tolik\Documents\vosk-model-en-us-0.22"
SAMPLE_RATE = 16000

audio_queue = queue.Queue()

stop_event = threading.Event()

def on_audio(indata, frames, time_info, status):
    if status:
        print(status)
    audio_queue.put(bytes(indata))

model = Model(MODEL_PATH)
recognizer = KaldiRecognizer(model, SAMPLE_RATE)

print("Слушаю...")

def listen_for_start():
    with sd.RawInputStream(
        samplerate=SAMPLE_RATE,
        blocksize=8000,
        dtype="int16",
        channels=1,
        callback=on_audio,
    ):
        while True:
            audio = audio_queue.get()

            if not recognizer.AcceptWaveform(audio):
                continue

            result = json.loads(recognizer.Result())
            text = result.get("text", "")
            if text:
                print("Итог:", text)

            if "is open" in text:
                return text

            

def make_data_handler():
    def on_data(_, data):
        if not data or data[0] != 0x01:
            return
        global curr_shape
        text = bytes(data[1:]).decode(errors="ignore")

        for line in text.splitlines():
            line = line.strip()
            if line and line != "rdy":
                print(f"Хаб: {line}")
    return on_data


async def send(client, text):
    data = (text + "\n").encode()
    for offset in range(0, len(data), CHUNK):
        await client.write_gatt_char(UART, b"\x06" + data[offset:offset + CHUNK], response=True)


async def control_robot():
    hub_name = "inspiro 2"
    device = await BleakScanner.find_device_by_name(hub_name, timeout=10)
    if device is None:
        print(f"Хаб {hub_name} не найден")
        return

    async with BleakClient(device) as client:
        await client.start_notify(UART, make_data_handler(2))
        await client.write_gatt_char(UART, b"\x01", response=True)
        print(f"Хаб {hub_name} готов")
        
        failures = 0
        try:
            while not stop_event.is_set():
                try:
                    if "forward" in listen_for_start():
                        await send (client, "FWD")
                    elif "backward" in listen_for_start():
                        await send (client, "BWD")
                    elif "sound" in listen_for_start():
                        playsound3.playsound(CONNECTED_PATH, block=False)
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

async def ble():
    await asyncio.gather(*(control_robot()))


def run_ble():
    try:
        asyncio.run(ble())
    except Exception as exc:
        print(f"Ошибка Bluetooth: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    ble_thread = threading.Thread(target=run_ble, daemon=True)
    ble_thread.start()

    try:
        listen_for_start()
    finally:
        stop_event.set()
        ble_thread.join(timeout=5)