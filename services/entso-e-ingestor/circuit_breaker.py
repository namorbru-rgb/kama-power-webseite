"""Simple in-memory circuit breaker for ENTSO-E API calls."""
import time
from enum import Enum


class State(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout_sec: float = 300.0) -> None:
        self._threshold = failure_threshold
        self._timeout = recovery_timeout_sec
        self._failures = 0
        self._state = State.CLOSED
        self._opened_at: float = 0.0

    @property
    def state(self) -> State:
        if self._state is State.OPEN:
            if time.monotonic() - self._opened_at >= self._timeout:
                self._state = State.HALF_OPEN
        return self._state

    def is_open(self) -> bool:
        return self.state is State.OPEN

    def record_success(self) -> None:
        self._failures = 0
        self._state = State.CLOSED

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self._threshold:
            self._state = State.OPEN
            self._opened_at = time.monotonic()
