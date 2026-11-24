import json
import queue

import sounddevice as sd
from vosk import Model, KaldiRecognizer

MODEL_PATH = r"C:\Users\tolik\Documents\vosk-model-small-en-us-0.15\vosk-model-small-en-us-0.15"
SAMPLE_RATE = 16000

audio_queue = queue.Queue()

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

            if recognizer.AcceptWaveform(audio):
                result = json.loads(recognizer.Result())
                text = result.get("text", "")
                if text:
                    print("Итог:", text)

                if "open" in text:
                    return text

            else:
                partial = json.loads(recognizer.PartialResult())
                partial_text = partial.get("partial", "")
                if partial_text:
                    print(f"Услышано: {partial_text}", end="", flush=True)
