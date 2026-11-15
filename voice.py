import json
import queue

import sounddevice as sd
from vosk import Model, KaldiRecognizer

MODEL_PATH = r"vosk-model-en-us-0.22"
SAMPLE_RATE = 16000

audio_queue = queue.Queue()

def on_audio(indata, frames, time_info, status):
    if status:
        print(status)
    audio_queue.put(bytes(indata))

model = Model(MODEL_PATH)
recognizer = KaldiRecognizer(model, SAMPLE_RATE)

print("Слушаю...")

try:
    with sd.RawInputStream(
        samplerate=SAMPLE_RATE,
        blocksize=8000,
        dtype="int16",
        channels=1,
        callback=on_audio,
    ):
        while True:
            audio = audio_queue.get()

            if recognizer.AcceptWaveform(audio):
                result = json.loads(recognizer.Result())
                if result.get("text"):
                    print("Итог:", result["text"])
            else:
                partial = json.loads(recognizer.PartialResult())
                if partial.get("partial"):
                    print("Пока услышано:", partial["partial"])

except KeyboardInterrupt:
    final_result = json.loads(recognizer.FinalResult())
    if final_result.get("text"):
        print("Итог:", final_result["text"])
    print("\nStopped.")