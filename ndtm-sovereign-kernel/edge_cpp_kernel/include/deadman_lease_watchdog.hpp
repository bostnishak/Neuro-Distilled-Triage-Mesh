#pragma once

#include "seqlock_epoch_arena.hpp"
#include <thread>
#include <atomic>
#include <chrono>

namespace ndtm::edge {

class DeadManLeaseWatchdog {
public:
    explicit DeadManLeaseWatchdog(SeqLockEpochArena& arena, std::chrono::milliseconds check_interval = std::chrono::milliseconds(10));
    ~DeadManLeaseWatchdog();

    DeadManLeaseWatchdog(const DeadManLeaseWatchdog&) = delete;
    DeadManLeaseWatchdog& operator=(const DeadManLeaseWatchdog&) = delete;

    void start();
    void stop();
    [[nodiscard]] bool is_running() const noexcept;
    [[nodiscard]] uint32_t total_reclaims() const noexcept;

private:
    void watchdog_loop();

    SeqLockEpochArena& arena_;
    std::chrono::milliseconds check_interval_;
    std::atomic<bool> running_{false};
    std::atomic<uint32_t> local_reclaims_count_{0};
    std::thread worker_thread_;
};

} // namespace ndtm::edge
