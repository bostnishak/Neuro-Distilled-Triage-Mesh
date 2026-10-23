#pragma once

#include <cstdint>
#include <cstddef>
#include <atomic>
#include <string>
#include <memory>

namespace ndtm::edge {

constexpr uint32_t SEQLOCK_ARENA_MAGIC = 0x4E445351; // "NDSQ" (NDTM SeqLock)
constexpr size_t SEQLOCK_SLOT_COUNT = 64;
constexpr size_t SEQLOCK_SLOT_PAYLOAD_SIZE = 1048576; // 1 MB contiguous float32 tensor
constexpr uint64_t DEADMAN_LEASE_TIMEOUT_NS = 50'000'000ULL; // 50 ms lease timeout
constexpr size_t CACHE_LINE = 64;

enum class SeqLockSlotState : uint32_t {
    FREE = 0,
    WRITING = 1,
    COMMITTED = 2,
    RECLAIMED = 3
};

// 128-byte cache-aligned slot header with sequence lock and dead-man lease
struct alignas(CACHE_LINE) SeqLockSlotHeader {
    std::atomic<uint64_t> seq_version{0};       // Even = valid committed data, Odd = write in-progress
    std::atomic<uint32_t> state{0};             // SeqLockSlotState
    uint32_t slot_id{0};
    std::atomic<uint64_t> writer_heartbeat_ns{0}; // Epoch timestamp (nanoseconds)
    std::atomic<int32_t> writer_pid{0};         // PID of active writing thread/process
    uint32_t payload_bytes{0};                  // Size of float32 tensor in bytes
    uint64_t payload_checksum{0};               // Fast xxHash or 64-bit checksum
    char telemetry_tag[32]{0};                  // Null-terminated telemetry stream tag
    uint8_t _padding[CACHE_LINE - ((sizeof(std::atomic<uint64_t>) * 2 + sizeof(std::atomic<uint32_t>) + sizeof(uint32_t) * 2 + sizeof(std::atomic<int32_t>) + sizeof(uint64_t) + 32) % CACHE_LINE)]{0};
};

// Control block located at offset 0 of shared memory arena
struct alignas(CACHE_LINE) SeqLockArenaControlBlock {
    uint32_t magic{SEQLOCK_ARENA_MAGIC};
    uint32_t slot_count{SEQLOCK_SLOT_COUNT};
    uint32_t slot_payload_size{static_cast<uint32_t>(SEQLOCK_SLOT_PAYLOAD_SIZE)};
    uint32_t total_reclaims_count{0};
    std::atomic<uint64_t> global_epoch{0};
    uint8_t _reserved[CACHE_LINE - (sizeof(uint32_t) * 4 + sizeof(std::atomic<uint64_t>))]{0};
};

class SeqLockEpochArena {
public:
    explicit SeqLockEpochArena(std::string arena_name = "/ndtm_seqlock_arena");
    ~SeqLockEpochArena();

    SeqLockEpochArena(const SeqLockEpochArena&) = delete;
    SeqLockEpochArena& operator=(const SeqLockEpochArena&) = delete;

    bool initialize_or_attach(bool is_creator = true);
    void detach_and_cleanup();

    // Writer API: Lock-Free SeqLock Write with Epoch Heartbeat
    int32_t acquire_free_slot();
    bool write_tensor_start(uint32_t slot_id, const std::string& tag, int32_t pid);
    bool write_tensor_commit(uint32_t slot_id, const float* tensor_data, size_t element_count);

    // Watchdog Reclaim API: Force-reclaims zombie slots if writer died mid-write
    bool force_reclaim_if_expired(uint32_t slot_id, uint64_t now_ns);

    [[nodiscard]] SeqLockSlotHeader* get_slot_header(uint32_t slot_id) noexcept;
    [[nodiscard]] float* get_slot_payload(uint32_t slot_id) noexcept;
    [[nodiscard]] const SeqLockSlotHeader* get_slot_header(uint32_t slot_id) const noexcept;
    [[nodiscard]] const float* get_slot_payload(uint32_t slot_id) const noexcept;
    [[nodiscard]] size_t total_size_bytes() const noexcept;

private:
    std::string arena_name_;
    bool is_creator_{false};
    void* mapped_base_{nullptr};
    size_t mapped_size_{0};
#if defined(_WIN32) || defined(_WIN64)
    void* win_shm_handle_{nullptr};
#else
    int posix_shm_fd_{-1};
#endif
};

} // namespace ndtm::edge
