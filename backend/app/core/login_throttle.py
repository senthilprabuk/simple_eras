import time
from collections import defaultdict, deque
from typing import Deque, Dict, Tuple

from app.core.config import settings

class LoginThrottle:
    """
    Sliding-window count of failed sign-ins, per (client, account) and per client.

    Keyed on the client as well as the account so that an attacker cannot lock a
    clinician out of their own account from elsewhere. State is per process: with
    several workers each keeps its own count, so the effective limit multiplies.
    """

    def __init__(self, max_per_account: int, max_per_client: int, window_secs: int):
        self.max_per_account = max_per_account
        self.max_per_client = max_per_client
        self.window_secs = window_secs
        self._by_account: Dict[Tuple[str, str], Deque[float]] = defaultdict(deque)
        self._by_client: Dict[str, Deque[float]] = defaultdict(deque)

    def _recent(self, attempts: Deque[float]) -> int:
        cutoff = time.monotonic() - self.window_secs
        while attempts and attempts[0] < cutoff:
            attempts.popleft()
        return len(attempts)

    def is_blocked(self, client: str, email: str) -> bool:
        return (
            self._recent(self._by_account[(client, email)]) >= self.max_per_account
            or self._recent(self._by_client[client]) >= self.max_per_client
        )

    def record_failure(self, client: str, email: str) -> None:
        now = time.monotonic()
        self._by_account[(client, email)].append(now)
        self._by_client[client].append(now)

    def record_success(self, client: str, email: str) -> None:
        self._by_account.pop((client, email), None)

    def clear(self) -> None:
        self._by_account.clear()
        self._by_client.clear()

login_throttle = LoginThrottle(
    max_per_account=settings.LOGIN_MAX_FAILURES_PER_ACCOUNT,
    max_per_client=settings.LOGIN_MAX_FAILURES_PER_CLIENT,
    window_secs=settings.LOGIN_FAILURE_WINDOW_SECS,
)
