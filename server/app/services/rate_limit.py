import time
from collections import defaultdict, deque


class RequestRateLimiter:
    def __init__(self) -> None:
        self._requests: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key_id: str, rpm: int) -> int | None:
        now = time.monotonic()
        window = self._requests[key_id]
        while window and window[0] <= now - 60:
            window.popleft()
        if len(window) >= rpm:
            return max(1, int(60 - (now - window[0])))
        window.append(now)
        return None


class LoginRateLimiter:
    def __init__(self, attempts: int = 5) -> None:
        self.limit = attempts
        self._attempts: dict[str, deque[float]] = defaultdict(deque)

    def blocked(self, ip: str) -> bool:
        now = time.monotonic()
        attempts = self._attempts[ip]
        while attempts and attempts[0] <= now - 60:
            attempts.popleft()
        return len(attempts) >= self.limit

    def fail(self, ip: str) -> None:
        self._attempts[ip].append(time.monotonic())

    def clear(self, ip: str) -> None:
        self._attempts[ip].clear()
