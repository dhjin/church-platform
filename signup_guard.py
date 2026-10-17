"""회원가입 스팸 방어.

- 차단 이메일 도메인(BLOCKED_EMAIL_DOMAINS 환경변수로 추가 가능, 하위 도메인 포함)
- 숨은 입력칸(honeypot): 사람은 비워 두고 자동 가입 봇은 채운다
- IP 별 가입 횟수 제한(메모리, 파드 단위)
"""
import os
import threading
import time
from collections import defaultdict, deque

DEFAULT_BLOCKED_DOMAINS = {"immenseignite.info"}
SIGNUP_LIMIT = int(os.getenv("SIGNUP_LIMIT_PER_IP", "3"))
SIGNUP_WINDOW_SEC = int(os.getenv("SIGNUP_WINDOW_SEC", "3600"))


def blocked_domains() -> set:
    extra = os.getenv("BLOCKED_EMAIL_DOMAINS", "")
    return DEFAULT_BLOCKED_DOMAINS | {d.strip().lower() for d in extra.split(",") if d.strip()}


def is_blocked_email(email: str) -> bool:
    domain = email.rsplit("@", 1)[-1].strip().lower().rstrip(".")
    return any(domain == d or domain.endswith("." + d) for d in blocked_domains())


def is_honeypot_filled(value) -> bool:
    return bool(value and str(value).strip())


class RateLimiter:
    def __init__(self, limit: int = SIGNUP_LIMIT, window: int = SIGNUP_WINDOW_SEC):
        self.limit, self.window = limit, window
        self._hits = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, now: float = None) -> bool:
        now = time.time() if now is None else now
        with self._lock:
            q = self._hits[key]
            while q and q[0] <= now - self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True


signup_limiter = RateLimiter()
