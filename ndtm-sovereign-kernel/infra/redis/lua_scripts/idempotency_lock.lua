-- ==============================================================================
-- NDTM-9000 SOVEREIGN KERNEL — ATOMIC IDEMPOTENCY LOCK & BODY CACHE BARRIER
-- Protects State-Mutating APIs from Double-Submissions and Race Conditions
-- ==============================================================================
-- KEYS[1]: Idempotency key (e.g., "idemp:uuid-12345678")
-- ARGV[1]: Command ("ACQUIRE" or "COMMIT")
-- ARGV[2]: (For ACQUIRE: payload_hash) | (For COMMIT: status_code)
-- ARGV[3]: (For ACQUIRE: lock_ttl_sec) | (For COMMIT: response_json_body)
-- ARGV[4]: (For COMMIT: cache_ttl_sec)

local key = KEYS[1]
local op = ARGV[1]

if op == "ACQUIRE" then
    local payload_hash = ARGV[2]
    local lock_ttl = tonumber(ARGV[3] or "30")

    local existing = redis.call("GET", key)
    if not existing then
        -- Atomically acquire in-flight lock
        local record = '{"status":"IN_FLIGHT","hash":"' .. payload_hash .. '"}'
        redis.call("SET", key, record, "EX", lock_ttl)
        return {"ACQUIRED", "0"}
    else
        -- Check state of existing lock
        if string.find(existing, '"status":"IN_FLIGHT"') then
            return {"CONFLICT_IN_FLIGHT", existing}
        elseif string.find(existing, '"status":"COMPLETED"') then
            -- Verify payload hash integrity
            if string.find(existing, payload_hash) then
                return {"COMPLETED", existing}
            else
                return {"MISMATCHED_PAYLOAD", existing}
            end
        else
            return {"UNKNOWN_STATE", existing}
        end
    end

elseif op == "COMMIT" then
    local status_code = ARGV[2]
    local response_body = ARGV[3]
    local cache_ttl = tonumber(ARGV[4] or "86400")

    -- Replace IN_FLIGHT lock with COMPLETED response cache
    local record = '{"status":"COMPLETED","code":' .. status_code .. ',"body":' .. response_body .. '}'
    redis.call("SET", key, record, "EX", cache_ttl)
    return {"COMMITTED", "1"}

elseif op == "RELEASE" then
    -- Used in case of catastrophic internal failure before commit
    redis.call("DEL", key)
    return {"RELEASED", "1"}

else
    return {"ERROR_UNKNOWN_OP", "0"}
end
