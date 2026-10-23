#include "shm_zero_copy_arena.hpp"

#include <iostream>
#include <stdexcept>
#include <system_error>

#if defined(_WIN32)
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#else
#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#endif

namespace ndtm::edge {

ShmZeroCopyArena::ShmZeroCopyArena() = default;

ShmZeroCopyArena::~ShmZeroCopyArena() {
    detach();
}

ShmZeroCopyArena::ShmZeroCopyArena(ShmZeroCopyArena&& other) noexcept
    : arena_name_(std::move(other.arena_name_)),
      arena_size_bytes_(other.arena_size_bytes_),
      shm_fd_(other.shm_fd_),
      mapped_ptr_(other.mapped_ptr_),
      control_block_(other.control_block_),
      slots_base_ptr_(other.slots_base_ptr_),
      is_creator_(other.is_creator_) {
    other.shm_fd_ = -1;
    other.mapped_ptr_ = nullptr;
    other.control_block_ = nullptr;
    other.slots_base_ptr_ = nullptr;
    other.is_creator_ = false;
}

ShmZeroCopyArena& ShmZeroCopyArena::operator=(ShmZeroCopyArena&& other) noexcept {
    if (this != &other) {
        detach();
        arena_name_ = std::move(other.arena_name_);
        arena_size_bytes_ = other.arena_size_bytes_;
        shm_fd_ = other.shm_fd_;
        mapped_ptr_ = other.mapped_ptr_;
        control_block_ = other.control_block_;
        slots_base_ptr_ = other.slots_base_ptr_;
        is_creator_ = other.is_creator_;

        other.shm_fd_ = -1;
        other.mapped_ptr_ = nullptr;
        other.control_block_ = nullptr;
        other.slots_base_ptr_ = nullptr;
        other.is_creator_ = false;
    }
    return *this;
}

bool ShmZeroCopyArena::create_or_attach(const std::string& arena_name, size_t size_mb) {
    arena_name_ = arena_name;
    arena_size_bytes_ = size_mb * 1024 * 1024;

#if defined(_WIN32)
    std::string win_mapping_name = "Local\\" + (arena_name.empty() || arena_name[0] != '/' ? arena_name : arena_name.substr(1));
    HANDLE hMapFile = CreateFileMappingA(
        INVALID_HANDLE_VALUE,
        NULL,
        PAGE_READWRITE,
        0,
        static_cast<DWORD>(arena_size_bytes_),
        win_mapping_name.c_str()
    );

    if (hMapFile == NULL) {
        return false;
    }

    is_creator_ = (GetLastError() != ERROR_ALREADY_EXISTS);

    mapped_ptr_ = MapViewOfFile(
        hMapFile,
        FILE_MAP_ALL_ACCESS,
        0,
        0,
        arena_size_bytes_
    );

    if (!mapped_ptr_) {
        CloseHandle(hMapFile);
        return false;
    }

    shm_fd_ = reinterpret_cast<intptr_t>(hMapFile);

#else
    shm_fd_ = shm_open(arena_name_.c_str(), O_CREAT | O_RDWR, 0600);
    if (shm_fd_ < 0) {
        return false;
    }

    struct stat sb{};
    if (fstat(shm_fd_, &sb) == 0 && sb.st_size < static_cast<off_t>(arena_size_bytes_)) {
        if (ftruncate(shm_fd_, static_cast<off_t>(arena_size_bytes_)) != 0) {
            close(shm_fd_);
            shm_fd_ = -1;
            return false;
        }
        is_creator_ = true;
    }

    mapped_ptr_ = mmap(
        nullptr,
        arena_size_bytes_,
        PROT_READ | PROT_WRITE,
        MAP_SHARED,
        shm_fd_,
        0
    );

    if (mapped_ptr_ == MAP_FAILED) {
        mapped_ptr_ = nullptr;
        close(shm_fd_);
        shm_fd_ = -1;
        return false;
    }
#endif

    control_block_ = reinterpret_cast<ArenaControlBlock*>(mapped_ptr_);
    slots_base_ptr_ = reinterpret_cast<uint8_t*>(mapped_ptr_) + sizeof(ArenaControlBlock);

    if (is_creator_) {
        control_block_->magic_header = NDTM_SHM_MAGIC;
        control_block_->total_slots = static_cast<uint32_t>((arena_size_bytes_ - sizeof(ArenaControlBlock)) / DEFAULT_SLOT_SIZE);
        control_block_->slot_size_bytes = static_cast<uint32_t>(DEFAULT_SLOT_SIZE);
        control_block_->write_seq.store(0, std::memory_order_relaxed);
        control_block_->read_seq.store(0, std::memory_order_relaxed);
    }

    return true;
}

void ShmZeroCopyArena::detach() {
    if (mapped_ptr_) {
#if defined(_WIN32)
        UnmapViewOfFile(mapped_ptr_);
        if (shm_fd_ != -1) {
            CloseHandle(reinterpret_cast<HANDLE>(shm_fd_));
            shm_fd_ = -1;
        }
#else
        munmap(mapped_ptr_, arena_size_bytes_);
        if (shm_fd_ >= 0) {
            close(shm_fd_);
            shm_fd_ = -1;
        }
#endif
        mapped_ptr_ = nullptr;
        control_block_ = nullptr;
        slots_base_ptr_ = nullptr;
    }
}

void ShmZeroCopyArena::cleanup() {
    detach();
#if !defined(_WIN32)
    if (!arena_name_.empty()) {
        shm_unlink(arena_name_.c_str());
    }
#endif
}

uint64_t ShmZeroCopyArena::get_write_seq() const noexcept {
    return control_block_ ? control_block_->write_seq.load(std::memory_order_acquire) : 0;
}

uint64_t ShmZeroCopyArena::get_read_seq() const noexcept {
    return control_block_ ? control_block_->read_seq.load(std::memory_order_acquire) : 0;
}

uint8_t* ShmZeroCopyArena::get_raw_slot_ptr(uint32_t slot_idx) noexcept {
    if (!control_block_ || slot_idx >= control_block_->total_slots) {
        return nullptr;
    }
    return slots_base_ptr_ + (static_cast<size_t>(slot_idx) * control_block_->slot_size_bytes);
}

const uint8_t* ShmZeroCopyArena::get_raw_slot_ptr(uint32_t slot_idx) const noexcept {
    if (!control_block_ || slot_idx >= control_block_->total_slots) {
        return nullptr;
    }
    return slots_base_ptr_ + (static_cast<size_t>(slot_idx) * control_block_->slot_size_bytes);
}

bool ShmZeroCopyArena::write_tensor_slot(
    uint32_t slot_idx,
    const SlotHeader& header,
    std::span<const float> tensor_data
) {
    uint8_t* slot_ptr = get_raw_slot_ptr(slot_idx);
    if (!slot_ptr) {
        return false;
    }

    const size_t required_bytes = sizeof(SlotHeader) + (tensor_data.size() * sizeof(float));
    if (required_bytes > control_block_->slot_size_bytes) {
        return false; // Exceeds 1MB slot boundary
    }

    // Write SlotHeader
    std::memcpy(slot_ptr, &header, sizeof(SlotHeader));

    // Write Contiguous Float32 Tensor Payload
    if (!tensor_data.empty()) {
        std::memcpy(slot_ptr + sizeof(SlotHeader), tensor_data.data(), tensor_data.size() * sizeof(float));
    }

    // Release memory fence to ensure memory is visible before incrementing write sequence
    std::atomic_thread_fence(std::memory_order_release);
    control_block_->write_seq.fetch_add(1, std::memory_order_acq_rel);

    return true;
}

bool ShmZeroCopyArena::read_tensor_slot(
    uint32_t slot_idx,
    SlotHeader& out_header,
    std::vector<float>& out_data
) {
    const uint8_t* slot_ptr = get_raw_slot_ptr(slot_idx);
    if (!slot_ptr) {
        return false;
    }

    // Acquire memory fence
    std::atomic_thread_fence(std::memory_order_acquire);

    std::memcpy(&out_header, slot_ptr, sizeof(SlotHeader));
    if (out_header.magic_header != NDTM_SHM_MAGIC) {
        return false;
    }

    size_t element_count = 1;
    for (int i = 0; i < 4; ++i) {
        if (out_header.shape[i] > 0) {
            element_count *= out_header.shape[i];
        }
    }

    const size_t total_payload_bytes = element_count * sizeof(float);
    if (sizeof(SlotHeader) + total_payload_bytes > control_block_->slot_size_bytes) {
        return false;
    }

    out_data.resize(element_count);
    std::memcpy(out_data.data(), slot_ptr + sizeof(SlotHeader), total_payload_bytes);

    return true;
}

} // namespace ndtm::edge
