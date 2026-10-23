import os
import time
from typing import Dict, Optional, Tuple
import redis.asyncio as aioredis
from core.config import settings
from core.exceptions import GCRAExceededException
from core.logging_otel import logger

# Path to Lua script
LUA_SCRIPT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "infra", "redis", "lua_scripts", "gcra_rate_limiter.lua"
)


class GCRARateLimiter:
    """Generic Cell Rate Algorithm (GCRA) Leaky Bucket Rate Limiter via Redis Lua script."""

    def __init__(self, redis_client: Optional[aioredis.Redis] = None):
        self._redis = redis_client
        self._lua_sha: Optional[str] = None
        self._script_content: Optional[str] = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        return self._redis

    async def _ensure_script_loaded(self) -> str:
        if self._lua_sha is not None:
            return self._lua_sha

        r = await self._get_redis()
        normalized_path = os.path.normpath(LUA_SCRIPT_PATH)
        if os.path.exists(normalized_path):
            with open(normalized_path, "r", encoding="utf-8") as f:
                self._script_content = f.read()
        else:
            # Fallback embedded Lua script
            self._script_content = """
            local key = KEYS[1]
            local rate_per_sec = tonumber(ARGV[1])
            local burst_capacity = tonumber(ARGV[2])
            local cost = tonumber(ARGV[3])
            local now_ms = tonumber(ARGV[4])
            local emission_interval = 1000.0 / rate_per_sec
            local tau = burst_capacity * emission_interval
            local tat = tonumber(redis.call('GET', key))
            if not tat then tat = now_ms end
            local new_tat = math.max(tat, now_ms) + (cost * emission_interval)
            local allow_at = new_tat - tau
            if allow_at <= now_ms then
                local ttl_ms = math.ceil((new_tat - now_ms) / 1000) + 1
                redis.call('SET', key, string.format('%.0f', new_tat), 'EX', math.max(ttl_ms, 1))
                local remaining = math.floor(math.max(0, (now_ms - (new_tat - tau)) / emission_interval))
                return {1, remaining, math.ceil(math.max(0, new_tat - now_ms)), 0}
            else
                local retry_after = math.ceil(allow_at - now_ms)
                return {0, 0, math.ceil(tat - now_ms), retry_after}
            end
            """

        self._lua_sha = await r.script_load(self._script_content)
        return self._lua_sha

    async def check_rate_limit(
        self,
        identifier: str,
        rate_per_sec: Optional[int] = None,
        burst_capacity: Optional[int] = None,
        cost: int = 1,
    ) -> Tuple[bool, Dict[str, int]]:
        """Checks rate limit for an identifier using GCRA.

        Returns (allowed, metadata_dict). Raises GCRAExceededException if exceeded.
        """
        rate = rate_per_sec or settings.GCRA_RATE_PER_SECOND
        burst = burst_capacity or settings.GCRA_BURST_CAPACITY
        now_ms = int(time.time() * 1000)
        key = f"gcra:{identifier}"

        try:
            r = await self._get_redis()
            sha = await self._ensure_script_loaded()
            result = await r.evalsha(sha, 1, key, rate, burst, cost, now_ms)

            # result: [allowed (0 or 1), remaining, reset_ms, retry_after_ms]
            allowed = bool(result[0] == 1)
            remaining = int(result[1])
            reset_ms = int(result[2])
            retry_after_ms = int(result[3])

            meta = {
                "limit": burst,
                "remaining": remaining,
                "reset_ms": reset_ms,
                "retry_after_ms": retry_after_ms,
            }

            if not allowed:
                raise GCRAExceededException(
                    f"GCRA Rate Limit Exceeded for {identifier}. Retry after {retry_after_ms}ms.",
                    retry_after_ms=retry_after_ms,
                )

            return True, meta

        except GCRAExceededException:
            raise
        except Exception as e:
            logger.warning("gcra_redis_bypass_warning", error=str(e), identifier=identifier)
            # Fail-open in event of Redis unavailability to avoid blocking critical incidents
            return True, {"limit": burst, "remaining": burst, "reset_ms": 0, "retry_after_ms": 0}
