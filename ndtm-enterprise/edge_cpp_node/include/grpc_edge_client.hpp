#pragma once

#include <string>
#include <vector>
#include <atomic>
#include <memory>

namespace ndtm::edge {

enum class ConnectionStatus {
    DISCONNECTED,
    CONNECTING,
    STREAMING,
    BACKOFF
};

struct EdgeTelemetryPacket {
    std::string node_id;
    int64_t timestamp_unix_ns{0};
    double sample_rate_hz{16000.0};
    std::vector<float> mel_bands;
    double spectral_entropy{0.0};
    double bearing_fault_harmonic{0.0};
    double anomaly_score{0.0};
    bool is_critical_alert{false};
};

class GrpcEdgeClient {
public:
    explicit GrpcEdgeClient(std::string target_endpoint = "backend:50051");
    ~GrpcEdgeClient();

    bool connect();
    void disconnect();

    /**
     * @brief Streams an analyzed anomaly telemetry packet to the central ingest pipeline.
     */
    bool send_sensor_frame(const EdgeTelemetryPacket& packet);

    /**
     * @brief Emits a heartbeat frame reporting edge hardware status and queue depths.
     */
    bool send_heartbeat(
        const std::string& node_id,
        double cpu_percent,
        uint32_t queue_depth,
        double last_infer_ms
    );

    [[nodiscard]] ConnectionStatus status() const noexcept { return status_.load(); }
    [[nodiscard]] uint64_t frames_sent() const noexcept { return frames_sent_.load(); }
    [[nodiscard]] const std::string& endpoint() const noexcept { return target_endpoint_; }

private:
    std::string target_endpoint_;
    std::atomic<ConnectionStatus> status_{ConnectionStatus::DISCONNECTED};
    std::atomic<uint64_t> frames_sent_{0};
};

} // namespace ndtm::edge
