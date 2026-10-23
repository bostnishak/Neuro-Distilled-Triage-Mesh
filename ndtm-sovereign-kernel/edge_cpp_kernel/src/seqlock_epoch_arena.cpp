#include "seqlock_epoch_arena.hpp"
#include <iostream>
#include <cstring>
#include <chrono>

#if defined(_WIN32) || defined(_WIN64)
#include <windows.h>
#else
#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#endif

namespace ndtm::edge {

static uint64_t current_time_nanoseconds() noexcept {
    auto now = std::chrono::steady_clock::now().time_since_epoch();
    return std::chrono::duration_cast<std::chrono::nanoseconds>(now).count();
}

static uint64_t compute_fast_checksum(const float* data, size_t count) noexcept {
    uint64_t hash = 0xcbf29ce484222325ULL;
    const uint8_t* byte_ptr = reinterpret_cast<const uint8_t*>(data);
    size_t byte_count = count * sizeof(float);
    for (size_t i = 0; i < byte_count; ++i) {
        hash ^= byte_ptr[i];
        hash *= 0x100000001b3ULL;
    }
    return hash;
}

SeqLockEpochArena::SeqLockEpochArena(std::string arena_name)
    : arena_name_(std::move(arena_name)) {
    // Total arena size: Control Block (aligned to CACHE_LINE) + N * (Header + Payload)
    size_t slot_total = sizeof(SeqLockSlotHeader) + SEQLOCK_SLOT_PAYLOAD_SIZE;
    mapped_size_ = sizeof(SeqLockArenaControlBlock) + (SEQLOCK_SLOT_COUNT * slot_total);
}

SeqLockEpochArena::~SeqLockEpochArena() {
    detach_and_cleanup();
}

size_t SeqLockEpochArena::total_size_bytes() const noexcept {
    return mapped_size_;
}

bool SeqLockEpochArena::initialize_or_attach(bool is_creator) {
    is_creator_ = is_creator;

#if defined(_WIN32) || defined(_WIN64)
    std::string win_map_name = "Local\\" + (arena_name_.empty() || arena_name_[0] != '/' ? arena_name_ : arena_name_.substr(1));

    if (is_creator_) {
        win_shm_handle_ = CreateFileMappingA(
            INVALID_HANDLE_VALUE,
            nullptr,
            PAGE_READWRITE,
            static_cast<DWORD>(mapped_size_ >> 32),
            static_cast<DWORD>(mapped_size_ & 0xFFFFFFFF),
            win_map_name.c_str()
        );
    } else {
        win_shm_handle_ = OpenFileMappingA(FILE_MAP_ALL_ACCESS, FALSE, win_map_name.c_str());
    }

    if (!win_shm_handle_) {
        return false;
    }

    mapped_base_ = MapViewOfFile(win_shm_handle_, FILE_MAP_ALL_ACCESS, 0, 0, mapped_size_);
    if (!mapped_base_) {
        CloseHandle(win_shm_handle_);
        win_shm_handle_ = nullptr;
        return false;
    }
#else
    int flags = is_creator_ ? (O_CREAT | O_RDWR) : O_RDWR;
    mode_t mode = 0666;
    posix_shm_fd_ = shm_open(arena_name_.c_str(), flags, mode);
    if (posix_shm_fd_ < 0) {
        return false;
    }

    if (is_creator_) {
        if (ftruncate(posix_shm_fd_, static_cast<off_t>(mapped_size_)) != 0) {
            close(posix_shm_fd_);
            posix_shm_fd_ = -1;
            return false;
        }
    }

    mapped_base_ = mmap(nullptr, mapped_size_, PROT_READ | PROT_WRITE, MAP_SHARED, posix_shm_fd_, 0);
    if (mapped_base_ == MAP_FAILED) {
        mapped_base_ = nullptr;
        close(posix_shm_fd_);
        posix_shm_fd_ = -1;
        return false;
    }
#endif

    if (is_creator_) {
        std::memset(mapped_base_, 0, mapped_size_);
        auto* ctrl = reinterpret_cast<SeqLockArenaControlBlock*>(mapped_base_);
        ctrl->magic = SEQLOCK_ARENA_MAGIC;
        ctrl->slot_count = static_cast<uint32_t>(SEQLOCK_SLOT_COUNT);
        ctrl->slot_payload_size = static_cast<uint32_t>(SEQLOCK_SLOT_PAYLOAD_SIZE);
        ctrl->total_reclaims_count = 0;
        ctrl->global_epoch.store(current_time_nanoseconds(), std::memory_order_release);

        for (uint32_t i = 0; i < SEQLOCK_SLOT_COUNT; ++i) {
            auto* hdr = get_slot_header(i);
            hdr->slot_id = i;
            hdr->state.store(static_cast<uint32_t>(SeqLockSlotState::FREE), std::memory_order_relaxed);
            hdr->seq_version.store(0, std::memory_order_relaxed);
        }
    }

    return true;
}

void SeqLockEpochArena::detach_and_cleanup() {
    if (mapped_base_) {
#if defined(_WIN32) || defined(_WIN64)
        UnmapViewOfFile(mapped_base_);
        mapped_base_ = nullptr;
        if (win_shm_handle_) {
            CloseHandle(win_shm_handle_);
            win_shm_handle_ = nullptr;
        }
#else
        munmap(mapped_base_, mapped_size_);
        mapped_base_ = nullptr;
        if (posix_shm_fd_ >= 0) {
            close(posix_shm_fd_);
            posix_shm_fd_ = -1;
        }
        if (is_creator_) {
            shm_unlink(arena_name_.c_str());
        }
#endif
    }
}

SeqLockSlotHeader* SeqLockEpochArena::get_slot_header(uint32_t slot_id) noexcept {
    if (!mapped_base_ || slot_id >= SEQLOCK_SLOT_COUNT) {
        return nullptr;
    }
    size_t slot_total = sizeof(SeqLockSlotHeader) + SEQLOCK_SLOT_PAYLOAD_SIZE;
    uint8_t* base = reinterpret_cast<uint8_t*>(mapped_base_) + sizeof(SeqLockArenaControlBlock);
    return reinterpret_cast<SeqLockSlotHeader*>(base + (slot_id * slot_total));
}

float* SeqLockEpochArena::get_slot_payload(uint32_t slot_id) noexcept {
    auto* hdr = get_slot_header(slot_id);
    if (!hdr) return nullptr;
    uint8_t* payload_base = reinterpret_cast<uint8_t*>(hdr) + sizeof(SeqLockSlotHeader);
    return reinterpret_cast<float*>(payload_base);
}

const SeqLockSlotHeader* SeqLockEpochArena::get_slot_header(uint32_t slot_id) const noexcept {
    return const_cast<SeqLockEpochArena*>(this)->get_slot_header(slot_id);
}

const float* SeqLockEpochArena::get_slot_payload(uint32_t slot_id) const noexcept {
    return const_cast<SeqLockEpochArena*>(this)->get_slot_payload(slot_id);
}

int32_t SeqLockEpochArena::acquire_free_slot() {
    for (uint32_t i = 0; i < SEQLOCK_SLOT_COUNT; ++i) {
        auto* hdr = get_slot_header(i);
        uint32_t expected = static_cast<uint32_t>(SeqLockSlotState::FREE);
        if (hdr->state.compare_exchange_strong(
                expected,
                static_cast<uint32_t>(SeqLockSlotState::WRITING),
                std::memory_order_acq_rel)) {
            return static_cast<int32_t>(i);
        }
    }
    return -1; // Arena full
}

bool SeqLockEpochArena::write_tensor_start(uint32_t slot_id, const std::string& tag, int32_t pid) {
    auto* hdr = get_slot_header(slot_id);
    if (!hdr) return false;

    // Step 1: Increment seq_version to make it ODD (Write In-Progress indicator)
    hdr->seq_version.fetch_add(1, std::memory_order_acq_rel);

    // Step 2: Update writer epoch and pid for dead-man lease monitoring
    hdr->writer_heartbeat_ns.store(current_time_nanoseconds(), std::memory_order_release);
    hdr->writer_pid.store(pid, std::memory_order_release);

    std::memset(hdr->telemetry_tag, 0, sizeof(hdr->telemetry_tag));
    std::strncpy(hdr->telemetry_tag, tag.c_str(), sizeof(hdr->telemetry_tag) - 1);

    return true;
}

bool SeqLockEpochArena::write_tensor_commit(uint32_t slot_id, const float* tensor_data, size_t element_count) {
    auto* hdr = get_slot_header(slot_id);
    float* payload = get_slot_payload(slot_id);
    if (!hdr || !payload || !tensor_data) return false;

    size_t byte_count = element_count * sizeof(float);
    if (byte_count > SEQLOCK_SLOT_PAYLOAD_SIZE) {
        return false;
    }

    // Step 3: Copy tensor payload and compute fast checksum
    std::memcpy(payload, tensor_data, byte_count);
    hdr->payload_bytes = static_cast<uint32_t>(byte_count);
    hdr->payload_checksum = compute_fast_checksum(tensor_data, element_count);

    // Step 4: Memory barrier ensuring all data writes are globally visible before closing the lock
    std::atomic_thread_fence(std::memory_order_release);

    // Step 5: Increment seq_version to make it EVEN (Valid Committed Read state)
    hdr->seq_version.fetch_add(1, std::memory_order_release);
    hdr->state.store(static_cast<uint32_t>(SeqLockSlotState::COMMITTED), std::memory_order_release);

    return true;
}

bool SeqLockEpochArena::force_reclaim_if_expired(uint32_t slot_id, uint64_t now_ns) {
    auto* hdr = get_slot_header(slot_id);
    if (!hdr) return false;

    uint64_t v = hdr->seq_version.load(std::memory_order_acquire);
    // Only check if write is in-progress (odd seq_version)
    if ((v & 1) != 0) {
        uint64_t heartbeat = hdr->writer_heartbeat_ns.load(std::memory_order_acquire);
        if (now_ns > heartbeat && (now_ns - heartbeat) > DEADMAN_LEASE_TIMEOUT_NS) {
            // Heartbeat expired! Writer thread crashed or stalled
            // Increment seq_version to make it EVEN to unblock optimistic readers
            hdr->seq_version.fetch_add(1, std::memory_order_release);
            hdr->state.store(static_cast<uint32_t>(SeqLockSlotState::FREE), std::memory_order_release);

            auto* ctrl = reinterpret_cast<SeqLockArenaControlBlock*>(mapped_base_);
            if (ctrl) {
                ctrl->total_reclaims_count++;
            }
            return true;
        }
    }
    return false;
}

} // namespace ndtm::edge
