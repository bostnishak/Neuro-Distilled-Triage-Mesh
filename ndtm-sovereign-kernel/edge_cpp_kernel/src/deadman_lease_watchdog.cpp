#include "deadman_lease_watchdog.hpp"
#include <iostream>

namespace ndtm::edge {

static uint64_t current_steady_ns() noexcept {
    auto now = std::chrono::steady_clock::now().time_since_epoch();
    return std::chrono::duration_cast<std::chrono::nanoseconds>(now).count();
}

DeadManLeaseWatchdog::DeadManLeaseWatchdog(SeqLockEpochArena& arena, std::chrono::milliseconds check_interval)
    : arena_(arena), check_interval_(check_interval) {}

DeadManLeaseWatchdog::~DeadManLeaseWatchdog() {
    stop();
}

void DeadManLeaseWatchdog::start() {
    if (!running_.exchange(true)) {
        worker_thread_ = std::thread(&DeadManLeaseWatchdog::watchdog_loop, this);
    }
}

void DeadManLeaseWatchdog::stop() {
    if (running_.exchange(false)) {
        if (worker_thread_.joinable()) {
            worker_thread_.join();
        }
    }
}

bool DeadManLeaseWatchdog::is_running() const noexcept {
    return running_.load(std::memory_order_relaxed);
}

uint32_t DeadManLeaseWatchdog::total_reclaims() const noexcept {
    return local_reclaims_count_.load(std::memory_order_relaxed);
}

void DeadManLeaseWatchdog::watchdog_loop() {
    while (running_.load(std::memory_order_relaxed)) {
        uint64_t now_ns = current_steady_ns();
        for (uint32_t i = 0; i < SEQLOCK_SLOT_COUNT; ++i) {
            if (arena_.force_reclaim_if_expired(i, now_ns)) {
                local_reclaims_count_.fetch_add(1, std::memory_order_relaxed);
            }
        }
        std::this_thread::sleep_for(check_interval_);
    }
}

} // namespace ndtm::edge
