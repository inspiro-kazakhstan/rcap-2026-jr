import time


class Stopwatch:
    def __init__(self):
        self._start_time = None
        self._elapsed = 0.0
        self.laps = []

    @property
    def running(self) -> bool:
        return self._start_time is not None

    @property
    def elapsed(self) -> float:
        if self.running:
            return self._elapsed + (time.perf_counter() - self._start_time)
        return self._elapsed

    def start(self):
        if not self.running:
            self._start_time = time.perf_counter()
        return self

    def stop(self) -> float:
        if self.running:
            self._elapsed += time.perf_counter() - self._start_time
            self._start_time = None
        return self.elapsed

    def reset(self):
        self._start_time = None
        self._elapsed = 0.0
        self.laps.clear()
        return self

    def restart(self):
        self.reset()
        self.start()
        return self

    def has_passed(self, seconds: float, auto_restart: bool = False) -> bool:
        if self.elapsed >= seconds:
            if auto_restart:
                self.restart()
            return True
        return False

    def remaining(self, seconds: float) -> float:
        return max(0.0, seconds - self.elapsed)

    def lap(self) -> float:
        current = self.elapsed
        last_total = sum(self.laps)
        lap_time = current - last_total
        self.laps.append(lap_time)
        return lap_time

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()
        print(f"Elapsed: {self.elapsed:.4f}s")
