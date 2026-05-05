from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from threading import Lock
from typing import Any


@dataclass(frozen=True)
class CoordinationDecision:
    allowed: bool
    reason: str | None = None
    retry_after_seconds: int | None = None


class LockHandle:
    def __init__(self, release_callback):
        self._release_callback = release_callback
        self._released = False

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        self._release_callback()

    def __enter__(self) -> "LockHandle":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


class InMemoryCoordinator:
    """Single-process coordinator used by local SQLite mode and deterministic tests."""

    backend_name = "memory"

    def __init__(self, *, namespace: str = "tradingagents:web"):
        self.namespace = namespace
        self._mutex = Lock()
        self._rate_hits: dict[tuple[str, str], list[float]] = {}
        self._budget_hits: dict[tuple[str, int], int] = {}
        self._locks: dict[str, tuple[str, float]] = {}
        self._idempotency: dict[str, tuple[dict[str, Any], float]] = {}

    def check_health(self) -> dict[str, Any]:
        return {"ok": True, "backend": self.backend_name}

    def check_rate_limit(self, scope: str, identity: str, *, limit: int, window_seconds: int) -> CoordinationDecision:
        if limit <= 0:
            return CoordinationDecision(True)
        now = time.monotonic()
        window_start = now - window_seconds
        with self._mutex:
            key = (scope, identity)
            hits = [hit for hit in self._rate_hits.get(key, []) if hit > window_start]
            if len(hits) >= limit:
                retry_after = max(1, int(window_seconds - (now - hits[0])))
                self._rate_hits[key] = hits
                return CoordinationDecision(False, "rate limit exceeded", retry_after)
            hits.append(now)
            self._rate_hits[key] = hits
        return CoordinationDecision(True)

    def try_consume_budget(self, *, user_id: int, workspace_id: int, user_limit: int, workspace_limit: int) -> CoordinationDecision:
        with self._mutex:
            user_key = ("user", user_id)
            workspace_key = ("workspace", workspace_id)
            user_count = self._budget_hits.get(user_key, 0)
            workspace_count = self._budget_hits.get(workspace_key, 0)
            if user_limit >= 0 and user_count >= user_limit:
                return CoordinationDecision(False, "user budget exceeded")
            if workspace_limit >= 0 and workspace_count >= workspace_limit:
                return CoordinationDecision(False, "workspace budget exceeded")
            self._budget_hits[user_key] = user_count + 1
            self._budget_hits[workspace_key] = workspace_count + 1
        return CoordinationDecision(True)

    def acquire_lock(self, name: str, *, ttl_seconds: int) -> LockHandle | None:
        now = time.monotonic()
        expires_at = now + ttl_seconds
        token = uuid.uuid4().hex
        with self._mutex:
            current = self._locks.get(name)
            if current and current[1] > now:
                return None
            self._locks[name] = (token, expires_at)

        def release() -> None:
            with self._mutex:
                current_lock = self._locks.get(name)
                if current_lock and current_lock[0] == token:
                    self._locks.pop(name, None)

        return LockHandle(release)

    def get_idempotent_response(self, key: str) -> dict[str, Any] | None:
        now = time.monotonic()
        with self._mutex:
            current = self._idempotency.get(key)
            if not current:
                return None
            response, expires_at = current
            if expires_at <= now:
                self._idempotency.pop(key, None)
                return None
            return dict(response)

    def store_idempotent_response(self, key: str, response: dict[str, Any], *, ttl_seconds: int) -> None:
        with self._mutex:
            self._idempotency[key] = (dict(response), time.monotonic() + ttl_seconds)


class RedisCoordinator:
    """Redis-backed cluster coordinator.

    The implementation uses Redis atomic primitives for production processes. Unit tests can
    pass an isolated fake client with compatible methods.
    """

    backend_name = "redis"

    def __init__(self, redis_url: str, *, namespace: str = "tradingagents:web", client: Any | None = None):
        self.namespace = namespace
        if client is not None:
            self.client = client
        else:
            import redis

            self.client = redis.Redis.from_url(redis_url, decode_responses=True)

    def _key(self, *parts: Any) -> str:
        return ":".join([self.namespace, *(str(part) for part in parts)])

    def check_health(self) -> dict[str, Any]:
        try:
            self.client.ping()
        except Exception as exc:  # pragma: no cover - concrete client failure varies by redis version
            raise ValueError("Redis configuration is invalid or unreachable") from exc
        return {"ok": True, "backend": self.backend_name}

    def check_rate_limit(self, scope: str, identity: str, *, limit: int, window_seconds: int) -> CoordinationDecision:
        if limit <= 0:
            return CoordinationDecision(True)
        bucket = int(time.time() // window_seconds)
        key = self._key("rate", scope, identity, bucket)
        count = int(self.client.incr(key))
        if count == 1:
            self.client.expire(key, window_seconds)
        if count > limit:
            return CoordinationDecision(False, "rate limit exceeded", window_seconds)
        return CoordinationDecision(True)

    def try_consume_budget(self, *, user_id: int, workspace_id: int, user_limit: int, workspace_limit: int) -> CoordinationDecision:
        user_key = self._key("budget", "user", user_id)
        workspace_key = self._key("budget", "workspace", workspace_id)
        user_count = int(self.client.get(user_key) or 0)
        workspace_count = int(self.client.get(workspace_key) or 0)
        if user_limit >= 0 and user_count >= user_limit:
            return CoordinationDecision(False, "user budget exceeded")
        if workspace_limit >= 0 and workspace_count >= workspace_limit:
            return CoordinationDecision(False, "workspace budget exceeded")
        self.client.incr(user_key)
        self.client.incr(workspace_key)
        return CoordinationDecision(True)

    def acquire_lock(self, name: str, *, ttl_seconds: int) -> LockHandle | None:
        key = self._key("lock", name)
        token = uuid.uuid4().hex
        acquired = self.client.set(key, token, nx=True, ex=ttl_seconds)
        if not acquired:
            return None

        def release() -> None:
            if self.client.get(key) == token:
                self.client.delete(key)

        return LockHandle(release)

    def get_idempotent_response(self, key: str) -> dict[str, Any] | None:
        value = self.client.get(self._key("idempotency", key))
        return json.loads(value) if value else None

    def store_idempotent_response(self, key: str, response: dict[str, Any], *, ttl_seconds: int) -> None:
        self.client.set(self._key("idempotency", key), json.dumps(response), ex=ttl_seconds)
