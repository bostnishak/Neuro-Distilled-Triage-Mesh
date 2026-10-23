-- ==============================================================================
-- NDTM-9000 SOVEREIGN KERNEL — GENERIC CELL RATE ALGORITHM (GCRA) RATE LIMITER
-- Atomic Leaky-Bucket Implementation with Microsecond Precision
-- ==============================================================================
-- KEYS[1]: Rate limit tracking key (e.g., "gcra:ip:192.168.1.10" or "gcra:user:uuid")
-- ARGV[1]: Rate (allowed cells / requests per period, e.g., 20)
-- ARGV[2]: Period in seconds (e.g., 1 for per-second, 60 for per-minute)
-- ARGV[3]: Burst capacity (e.g., 5 excess requests allowed)
-- ARGV[4]: Cost (number of units for current request, typically 1)

local key = KEYS[1]
local rate = tonumber(ARGV[1])
local period = tonumber(ARGV[2])
local burst = tonumber(ARGV[3])
local cost = tonumber(ARGV[4] or "1")

if not rate or rate <= 0 then rate = 20 end
if not period or period <= 0 then period = 1 end
if not burst or burst < 0 then burst = 5 end
if not cost or cost <= 0 then cost = 1 end

-- Calculate emission interval T (microseconds between each cell)
local emission_interval_us = math.floor((period * 1000000) / rate)

-- Burst tolerance tau in microseconds (maximum time debt allowed)
local burst_tolerance_us = burst * emission_interval_us

-- Fetch current synchronized server timestamp from Redis in microseconds
local time_res = redis.call("TIME")
local now_us = (tonumber(time_res[1]) * 1000000) + tonumber(time_res[2])

-- Retrieve current Theoretical Arrival Time (TAT)
local current_tat = redis.call("GET", key)
local tat_us

if not current_tat then
    tat_us = now_us
else
    tat_us = tonumber(current_tat)
    if not tat_us or tat_us < now_us then
        tat_us = now_us
    end
end

-- Calculate prospective new Theoretical Arrival Time after consuming cost
local increment_us = cost * emission_interval_us
local new_tat_us = tat_us + increment_us

-- Permitted if new_tat_us <= now_us + burst_tolerance_us
local allow_cutoff_us = now_us + burst_tolerance_us

if new_tat_us <= allow_cutoff_us then
    -- Request is ACCEPTED: Update TAT and set TTL based on recovery horizon
    local ttl_seconds = math.ceil((new_tat_us - now_us) / 1000000)
    if ttl_seconds < 1 then ttl_seconds = 1 end
    redis.call("SET", key, tostring(new_tat_us), "EX", ttl_seconds)

    -- Remaining burst capacity
    local remaining = math.floor((allow_cutoff_us - new_tat_us) / emission_interval_us)
    if remaining < 0 then remaining = 0 end

    -- Return: [allowed=1, remaining, retry_after_sec=0, reset_in_us]
    return {1, remaining, "0", tostring(new_tat_us - now_us)}
else
    -- Request is REJECTED (Rate limit exceeded)
    local retry_after_us = new_tat_us - allow_cutoff_us
    local retry_after_sec = retry_after_us / 1000000.0
    
    local remaining = 0
    local reset_in_us = tat_us - now_us
    if reset_in_us < 0 then reset_in_us = 0 end

    -- Return: [allowed=0, remaining=0, retry_after_sec, reset_in_us]
    return {0, remaining, tostring(retry_after_sec), tostring(reset_in_us)}
end
