#pragma once

#include "shm_zero_copy_arena.hpp"
#include "spsc_atomic_ring.hpp"
#include "radix2_fft_spectrogram.hpp"
#include "laplacian_simd_optics.hpp"

#include <memory>
#include <string>
#include <span>

namespace ndtm::edge {

struct IngestedTelemetryPacket {
    uint64_t timestamp_ns{0};
    uint32_t sensor_type{0}; // 1 = Audio Vibration, 2 = Optical Image
    std::vector<float> features;
    SlotHeader slot_header;
};

class GrpcTelemetryBridge {
public:
    explicit GrpcTelemetryBridge(const std::string& shm_arena_name = "/ndtm_tensor_arena");
    ~GrpcTelemetryBridge();

    bool initialize();
    void shutdown();

    // Ingests acoustic vibration sample, computes FFT & Mel energies, queues into SHM
    bool ingest_acoustic_stream(
        uint64_t timestamp_ns,
        const std::string& device_id,
        std::span<const float> pcm_samples
    );

    // Ingests camera image, computes Laplacian variance, strips EXIF, queues into SHM
    bool ingest_optical_frame(
        uint64_t timestamp_ns,
        std::span<const uint8_t> raw_jpeg,
        std::span<const uint8_t> grayscale_pixels,
        size_t width,
        size_t height
    );

    // Drains internal lock-free ring buffer into POSIX SHM slots
    size_t flush_ring_to_shm();

    ShmZeroCopyArena& get_arena() noexcept { return arena_; }
    SPSCAtomicRingBuffer<IngestedTelemetryPacket>& get_ring() noexcept { return ring_buffer_; }

private:
    std::string shm_name_;
    ShmZeroCopyArena arena_;
    SPSCAtomicRingBuffer<IngestedTelemetryPacket> ring_buffer_;
    Radix2FftAnalyzer fft_analyzer_;
    LaplacianSimdOptics optics_engine_;
    std::atomic<uint32_t> current_slot_idx_{0};
};

} // namespace ndtm::edge
