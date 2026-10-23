import hashlib
import json
import os
from typing import Any, Dict, Optional, Tuple
import redis.asyncio as aioredis
from core.config import settings
from core.exceptions import IdempotencyConflictException, ConflictError
from core.logging_otel import logger

LUA_IDEMPOTENCY_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "infra", "redis", "lua_scripts", "idempotency_lock.lua"
)


class IdempotencyBarrier:
    """Distributed Idempotency Barrier with SHA-256 payload verification and response replay."""

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
        normalized_path = os.path.normpath(LUA_IDEMPOTENCY_PATH)
        if os.path.exists(normalized_path):
            with open(normalized_path, "r", encoding="utf-8") as f:
                self._script_content = f.read()
        else:
            self._script_content = """
            local key = KEYS[1]
            local action = ARGV[1]
            local payload_hash = ARGV[2]
            local response_data = ARGV[3] or ''
            local ttl_seconds = tonumber(ARGV[4] or '120')

            if action == 'ACQUIRE' then
                local exists = redis.call('EXISTS', key)
                if exists == 0 then
                    redis.call('HSET', key, 'status', 'PROCESSING', 'hash', payload_hash)
                    redis.call('EXPIRE', key, ttl_seconds)
                    return {'ACQUIRED', ''}
                else
                    local current_hash = redis.call('HGET', key, 'hash')
                    if current_hash ~= payload_hash then
                        return {'PAYLOAD_MISMATCH', ''}
                    end
                    local status = redis.call('HGET', key, 'status')
                    if status == 'COMPLETED' then
                        local cached = redis.call('HGET', key, 'response') or ''
                        return {'CACHED', cached}
                    else
                        return {'LOCKED', ''}
                    end
                end
            elseif action == 'COMMIT' then
                redis.call('HSET', key, 'status', 'COMPLETED', 'response', response_data)
                redis.call('EXPIRE', key, 86400)
                return {'COMMITTED', ''}
            elseif action == 'RELEASE' then
                redis.call('DEL', key)
                return {'RELEASED', ''}
            end
            return {'INVALID_ACTION', ''}
            """

        self._lua_sha = await r.script_load(self._script_content)
        return self._lua_sha

    @classmethod
    def compute_hash(cls, payload: Any) -> str:
        canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    async def acquire_or_replay(
        self,
        idempotency_key: str,
        payload_data: Any,
        lock_ttl_seconds: int = 120,
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """Tries to acquire execution lock for idempotency key.

        If already COMPLETED: returns (False, cached_response_dict) for immediate replay.
        If successfully ACQUIRED: returns (True, None).
        If already PROCESSING: raises IdempotencyConflictException.
        If PAYLOAD_MISMATCH: raises ConflictError.
        """
        payload_hash = self.compute_hash(payload_data)
        redis_key = f"idempotency:{idempotency_key}"

        try:
            r = await self._get_redis()
            sha = await self._ensure_script_loaded()
            result = await r.evalsha(sha, 1, redis_key, "ACQUIRE", payload_hash, "", lock_ttl_seconds)

            status = str(result[0])
            cached_data = str(result[1])

            if status == "ACQUIRED":
                return True, None
            elif status == "CACHED":
                parsed = json.loads(cached_data) if cached_data else {}
                return False, parsed
            elif status == "LOCKED":
                raise IdempotencyConflictException(
                    f"A request with idempotency key '{idempotency_key}' is currently in progress."
                )
            elif status == "PAYLOAD_MISMATCH":
                raise ConflictError(
                    f"Idempotency key '{idempotency_key}' used with differing payload checksum."
                )
            else:
                return True, None

        except (IdempotencyConflictException, ConflictError):
            raise
        except Exception as e:
            logger.warning("idempotency_redis_error_bypass", error=str(e), key=idempotency_key)
            return True, None

    async def commit_response(
        self,
        idempotency_key: str,
        payload_data: Any,
        response_data: Dict[str, Any],
    ) -> None:
        payload_hash = self.compute_hash(payload_data)
        redis_key = f"idempotency:{idempotency_key}"
        try:
            r = await self._get_redis()
            sha = await self._ensure_script_loaded()
            resp_str = json.dumps(response_data)
            await r.evalsha(sha, 1, redis_key, "COMMIT", payload_hash, resp_str, 86400)
        except Exception as e:
            logger.warning("idempotency_commit_failed", error=str(e), key=idempotency_key)

    async def release_lock(self, idempotency_key: str) -> None:
        redis_key = f"idempotency:{idempotency_key}"
        try:
            r = await self._get_redis()
            sha = await self._ensure_script_loaded()
            await r.evalsha(sha, 1, redis_key, "RELEASE", "", "", 0)
        except Exception as e:
            logger.warning("idempotency_release_failed", error=str(e), key=idempotency_key)
