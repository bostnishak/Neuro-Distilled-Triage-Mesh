#include "grpc_telemetry_bridge.hpp"

#include <iostream>

namespace ndtm::edge {

GrpcTelemetryBridge::GrpcTelemetryBridge(const std::string& shm_arena_name)
    : shm_name_(shm_arena_name),
      fft_analyzer_(4096, 16000.0f),
      optics_engine_(85.0f) {}

GrpcTelemetryBridge::~GrpcTelemetryBridge() {
    shutdown();
}

bool GrpcTelemetryBridge::initialize() {
    return arena_.create_or_attach(shm_name_, 64);
}

void GrpcTelemetryBridge::shutdown() {
    arena_.detach();
}

bool GrpcTelemetryBridge::ingest_acoustic_stream(
    uint64_t timestamp_ns,
    const std::string& /*device_id*/,
    std::span<const float> pcm_samples
) {
    const auto spec = fft_analyzer_.analyze(pcm_samples);

    IngestedTelemetryPacket packet{};
    packet.timestamp_ns = timestamp_ns;
    packet.sensor_type = 1; // Audio Vibration

    // Pack 16 Mel bands as features
    packet.features.assign(spec.mel_energies, spec.mel_energies + 16);

    packet.slot_header.slot_id = timestamp_ns;
    packet.slot_header.magic_header = NDTM_SHM_MAGIC;
    packet.slot_header.shape[0] = 1;
    packet.slot_header.shape[1] = 1;
    packet.slot_header.shape[2] = 1;
    packet.slot_header.shape[3] = 16;
    packet.slot_header.laplacian_variance = 0.0f;
    packet.slot_header.spectral_entropy = spec.spectral_entropy;
    packet.slot_header.timestamp_ns = timestamp_ns;

    for (size_t i = 0; i < 16; ++i) {
        packet.slot_header.mel_bands[i] = spec.mel_energies[i];
    }

    return ring_buffer_.push(std::move(packet));
}

bool GrpcTelemetryBridge::ingest_optical_frame(
    uint64_t timestamp_ns,
    std::span<const uint8_t> raw_jpeg,
    std::span<const uint8_t> grayscale_pixels,
    size_t width,
    size_t height
) {
    const auto optics = optics_engine_.process_image(raw_jpeg, grayscale_pixels, width, height);
    if (optics.is_polyglot_detected) {
        return false; // Polyglot exploit intercepted
    }

    IngestedTelemetryPacket packet{};
    packet.timestamp_ns = timestamp_ns;
    packet.sensor_type = 2; // Optical Image

    packet.slot_header.slot_id = timestamp_ns;
    packet.slot_header.magic_header = NDTM_SHM_MAGIC;
    packet.slot_header.shape[0] = 1;
    packet.slot_header.shape[1] = 1;
    packet.slot_header.shape[2] = static_cast<uint32_t>(height);
    packet.slot_header.shape[3] = static_cast<uint32_t>(width);
    packet.slot_header.laplacian_variance = optics.laplacian_variance;
    packet.slot_header.spectral_entropy = 0.0f;
    packet.slot_header.timestamp_ns = timestamp_ns;

    return ring_buffer_.push(std::move(packet));
}

size_t GrpcTelemetryBridge::flush_ring_to_shm() {
    size_t flushed = 0;
    IngestedTelemetryPacket packet;

    while (ring_buffer_.pop(packet)) {
        const uint32_t slot = current_slot_idx_.fetch_add(1, std::memory_order_relaxed) % arena_.get_total_slots();
        arena_.write_tensor_slot(slot, packet.slot_header, packet.features);
        ++flushed;
    }

    return flushed;
}

} // namespace ndtm::edge
