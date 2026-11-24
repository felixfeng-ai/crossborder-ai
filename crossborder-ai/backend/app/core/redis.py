"""缓存与限流基础设施：Redis 连接、缓存辅助函数和降级行为。

VeyaShip - Cache Layer.

In-memory cache decorator with TTL support.
When Redis is available, it will be used instead."""

import asyncio
import functools
import hashlib
import json
import time
from typing import Any, Callable, Optional

# ── In-memory cache store ──────────────────────────────────────────
_cache_store: dict[str, tuple[float, Any]] = {}
_lock = asyncio.Lock()


async def cache_get(key: str) -> Optional[Any]:
    """Get a value from cache. Returns None if missing or expired."""
    async with _lock:
        entry = _cache_store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() > expires_at:
            del _cache_store[key]
            return None
        return value


async def cache_set(key: str, value: Any, ttl_seconds: int):
    """Set a value in cache with TTL."""
    async with _lock:
        _cache_store[key] = (time.monotonic() + ttl_seconds, value)


async def cache_clear(pattern: Optional[str] = None):
    """Clear cache entries. If pattern is None, clear all."""
    async with _lock:
        if pattern is None:
            _cache_store.clear()
        else:
            keys = [k for k in _cache_store if pattern in k]
            for k in keys:
                del _cache_store[k]


def cache(ttl: int = 600):
    """Decorator: cache async function results in memory.

    Args:
        ttl: Time-to-live in seconds (default 600 = 10 min).

    The cache key is derived from the function name + JSON-serialized args/kwargs.
    Only works on async functions.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Build cache key
            key_data = {
                "func": f"{func.__module__}.{func.__qualname__}",
                "args": [str(a) for a in args],
                "kwargs": {k: str(v) for k, v in sorted(kwargs.items())},
            }
            key = hashlib.md5(
                json.dumps(key_data, sort_keys=True).encode()
            ).hexdigest()

            # Try cache
            cached = await cache_get(key)
            if cached is not None:
                return cached

            # Compute
            result = await func(*args, **kwargs)

            # Store
            await cache_set(key, result, ttl)
            return result

        return wrapper

    return decorator
