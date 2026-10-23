#pragma once

#include <cstdint>
#include <cstddef>
#include <string>
#include <vector>
#include <atomic>
#include <cstring>
#include <span>

namespace ndtm::edge {

constexpr uint32_t NDTM_SHM_MAGIC = 0x4E44544D; // "NDTM"
constexpr size_t DEFAULT_SLOT_COUNT = 64;
constexpr size_t DEFAULT_SLOT_SIZE = 1024 * 1024; // 1 MB per slot

#pragma pack(push, 1)
struct SlotHeader {
    uint64_t slot_id{0};
    uint32_t magic_header{NDTM_SHM_MAGIC};
    uint32_t shape[4]{1, 1, 1, 1}; // N, C, H, W or Batch, Channels, SeqLen, Dim
    float laplacian_variance{0.0f};
    float spectral_entropy{0.0f};
    float mel_bands[16]{0.0f};
    uint8_t sha256_digest[32]{0};
    uint64_t timestamp_ns{0};
};
#pragma pack(pop)

struct alignas(64) ArenaControlBlock {
    std::atomic<uint64_t> write_seq{0};
    std::atomic<uint64_t> read_seq{0};
    uint32_t total_slots{DEFAULT_SLOT_COUNT};
    uint32_t slot_size_bytes{DEFAULT_SLOT_SIZE};
    uint32_t magic_header{NDTM_SHM_MAGIC};
    uint8_t _padding[40]{0};
};

class ShmZeroCopyArena {
public:
    ShmZeroCopyArena();
    ~ShmZeroCopyArena();

    // Delete copy operations (RAII resource handle)
    ShmZeroCopyArena(const ShmZeroCopyArena&) = delete;
    ShmZeroCopyArena& operator=(const ShmZeroCopyArena&) = delete;

    // Allow move operations
    ShmZeroCopyArena(ShmZeroCopyArena&& other) noexcept;
    ShmZeroCopyArena& operator=(ShmZeroCopyArena&& other) noexcept;

    bool create_or_attach(const std::string& arena_name, size_t size_mb = 64);
    void detach();
    void cleanup();

    bool is_attached() const noexcept { return mapped_ptr_ != nullptr; }
    size_t get_total_slots() const noexcept { return control_block_ ? control_block_->total_slots : 0; }
    size_t get_slot_size() const noexcept { return control_block_ ? control_block_->slot_size_bytes : 0; }
    uint64_t get_write_seq() const noexcept;
    uint64_t get_read_seq() const noexcept;

    bool write_tensor_slot(
        uint32_t slot_idx,
        const SlotHeader& header,
        std::span<const float> tensor_data
    );

    bool read_tensor_slot(
        uint32_t slot_idx,
        SlotHeader& out_header,
        std::vector<float>& out_data
    );

    uint8_t* get_raw_slot_ptr(uint32_t slot_idx) noexcept;
    const uint8_t* get_raw_slot_ptr(uint32_t slot_idx) const noexcept;

private:
    std::string arena_name_;
    size_t arena_size_bytes_{0};
    intptr_t shm_fd_{-1};
    void* mapped_ptr_{nullptr};
    ArenaControlBlock* control_block_{nullptr};
    uint8_t* slots_base_ptr_{nullptr};
    bool is_creator_{false};
};

} // namespace ndtm::edge
