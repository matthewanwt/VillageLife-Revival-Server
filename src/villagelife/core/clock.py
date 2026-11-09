"""Injectable clocks make time-based game logic deterministic in tests."""
import time
from dataclasses import dataclass


class SystemClock:
    def now(self) -> int:
        return int(time.time())


@dataclass
class FrozenClock:
    timestamp: int

    def now(self) -> int:
        return self.timestamp

    def advance(self, seconds: int) -> None:
        if seconds < 0:
            raise ValueError('Cannot move simulation clock backwards')
        self.timestamp += seconds
