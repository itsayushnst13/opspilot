"""Shared API dependencies: current user, in-memory rate limiting."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, Request

from ..core.security import get_current_user
from ..models import User

_lock = threading.Lock()
_hits: dict[str, deque] = defaultdict(deque)


def _check(key: str, limit: int, window_s: int) -> None:
    now = time.monotonic()
    with _lock:
        q = _hits[key]
        while q and now - q[0] > window_s:
            q.popleft()
        if len(q) >= limit:
            raise HTTPException(429, "Too many requests, slow down")
        q.append(now)


def reset_limits() -> None:
    with _lock:
        _hits.clear()


def upload_limit(user: User = Depends(get_current_user)) -> User:
    """30 workflow submissions per minute per user (single-process, in-memory)."""
    _check(f"up:{user.email}", 30, 60)
    return user


def login_limit(request: Request) -> None:
    ip = request.client.host if request.client else "?"
    _check(f"login:{ip}", 20, 60)
