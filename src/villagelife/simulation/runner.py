"""Hosted scheduling is optional. Offline catch-up calls the same coordinator."""
import threading
from dataclasses import dataclass


@dataclass
class Scheduler:
    coordinator: object
    poll_seconds: float = 5.0

    def start(self) -> None:
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name='vl-world-tick')
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.wait(self.poll_seconds):
            try:
                self.coordinator.advance_all()
            except Exception:
                # Must be visible in hosting logs; do not kill the scheduler.
                import logging
                logging.getLogger(__name__).exception('World tick failed')

    def stop(self) -> None:
        if hasattr(self, '_stop'):
            self._stop.set()
            self._thread.join(timeout=5)
