"""
cache.py — Zerops Valkey (Redis-compatible) caching layer for Signal.

Caches trend + YouTube signals by niche for 1 hour so:
  - Repeated scans of the same niche skip Google Trends entirely
    (pytrends is unofficial and rate-limits aggressively)
  - YouTube API quota isn't wasted on the same query twice
  - Response time drops from ~25s to <1s on cache hits

Fails soft: if Valkey isn't configured or is unreachable,
every function returns None/False and the app runs normally without caching.
This means local dev works with no Redis/Valkey installed.

On Zerops: add a Valkey service to your project and set VALKEY_HOST,
VALKEY_PORT, and VALKEY_PASSWORD in your Signal service's env variables.
"""

import os
import json
import time
import threading
import logging

try:
    import redis
    _REDIS_AVAILABLE = True
except ImportError:
    _REDIS_AVAILABLE = False

logger = logging.getLogger(__name__)

_CACHE_TTL = 3600          # 1 hour in seconds
_KEY_PREFIX = "signal:v1"  # bump version if data shape changes

# Thread-safe in-memory cache fallback (used when Redis/Valkey is not connected)
_MEMORY_CACHE = {}
_MEMORY_CACHE_LOCK = threading.Lock()


def get_cache():
    """
    Return a connected Redis/Valkey client, or None if not configured.
    Reads VALKEY_HOST (and optionally VALKEY_PORT, VALKEY_PASSWORD) from env.
    """
    if not _REDIS_AVAILABLE:
        return None

    host = os.getenv("VALKEY_HOST") or os.getenv("REDIS_HOST")
    if not host:
        return None

    port     = int(os.getenv("VALKEY_PORT") or os.getenv("REDIS_PORT") or 6379)
    password = os.getenv("VALKEY_PASSWORD") or os.getenv("REDIS_PASSWORD") or None

    try:
        client = redis.Redis(
            host=host,
            port=port,
            password=password,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        client.ping()
        return client
    except Exception as exc:
        logger.warning("Valkey not reachable (%s) — using in-memory cache fallback.", exc)
        return None


def _niche_key(niche: str) -> str:
    safe = niche.lower().strip().replace(" ", "_")[:80]
    return f"{_KEY_PREFIX}:signals:{safe}"


def get_cached_signals(niche: str, client) -> list | None:
    """Return cached signals for this niche (Redis or in-memory fallback), or None on miss."""
    key = _niche_key(niche)

    # 1. Try Redis/Valkey if connected
    if client is not None:
        try:
            raw = client.get(key)
            if raw is not None:
                logger.info("Redis cache HIT for niche: %s", niche)
                return json.loads(raw)
        except Exception as exc:
            logger.warning("Redis cache get failed: %s", exc)

    # 2. In-memory fallback
    with _MEMORY_CACHE_LOCK:
        if key in _MEMORY_CACHE:
            ts, data = _MEMORY_CACHE[key]
            if time.time() - ts < _CACHE_TTL:
                logger.info("In-memory cache HIT for niche: %s", niche)
                return json.loads(json.dumps(data))  # return clean deep copy
            else:
                del _MEMORY_CACHE[key]

    return None


def set_cached_signals(niche: str, signals: list, client, ttl: int = _CACHE_TTL) -> bool:
    """Store signals in Valkey and/or in-memory fallback with TTL. Returns True on success."""
    key = _niche_key(niche)
    success = False

    # Always populate in-memory fallback
    with _MEMORY_CACHE_LOCK:
        _MEMORY_CACHE[key] = (time.time(), signals)
        success = True

    # Try Redis/Valkey if client available
    if client is not None:
        try:
            client.setex(key, ttl, json.dumps(signals))
            logger.info("Redis cache SET for niche: %s (TTL %ds)", niche, ttl)
        except Exception as exc:
            logger.warning("Redis cache set failed: %s", exc)

    return success


def cache_status(client) -> dict:
    """Return a small dict describing cache health — used by /health endpoint."""
    with _MEMORY_CACHE_LOCK:
        active_memory_items = len(_MEMORY_CACHE)

    if client is None:
        return {
            "connected": False,
            "mode": "in-memory-fallback",
            "cached_items_count": active_memory_items
        }

    try:
        info = client.info("server")
        return {
            "connected": True,
            "mode": "redis",
            "version": info.get("redis_version", "unknown"),
            "cached_items_count": active_memory_items
        }
    except Exception as exc:
        return {
            "connected": False,
            "mode": "in-memory-fallback",
            "cached_items_count": active_memory_items,
            "reason": str(exc)
        }

