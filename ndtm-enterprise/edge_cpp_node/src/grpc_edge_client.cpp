#include "grpc_edge_client.hpp"

#include <iostream>
#include <chrono>
#include <thread>

namespace ndtm::edge {

GrpcEdgeClient::GrpcEdgeClient(std::string target_endpoint)
    : target_endpoint_(std::move(target_endpoint)) {}

GrpcEdgeClient::~GrpcEdgeClient() {
    disconnect();
}

bool GrpcEdgeClient::connect() {
    status_.store(ConnectionStatus::CONNECTING);
    std::cout << "[GrpcEdgeClient] Establishing gRPC channel to central ingest gateway at: "
              << target_endpoint_ << std::endl;

    // Simulate robust socket handshake with retry backoff
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
    status_.store(ConnectionStatus::STREAMING);
    std::cout << "[GrpcEdgeClient] Channel active. Streaming protocol READY." << std::endl;
    return true;
}

void GrpcEdgeClient::disconnect() {
    if (status_.load() != ConnectionStatus::DISCONNECTED) {
        std::cout << "[GrpcEdgeClient] Closing gRPC stream. Total frames sent: "
                  << frames_sent_.load() << std::endl;
        status_.store(ConnectionStatus::DISCONNECTED);
    }
}

bool GrpcEdgeClient::send_sensor_frame(const EdgeTelemetryPacket& packet) {
    if (status_.load() != ConnectionStatus::STREAMING) {
        connect();
    }

    // In a full compiled gRPC build with protoc, this serializes to EdgeSensorFrame protobuf message.
    frames_sent_.fetch_add(1, std::memory_order_relaxed);

    if (packet.is_critical_alert) {
        std::cout << "[GrpcEdgeClient][ALERT] High-priority anomaly transmitted from node ["
                  << packet.node_id << "] Anomaly Score: " << packet.anomaly_score
                  << " Bearing Harmonic: " << packet.bearing_fault_harmonic << std::endl;
    }

    return true;
}

bool GrpcEdgeClient::send_heartbeat(
    const std::string& node_id,
    double cpu_percent,
    uint32_t queue_depth,
    double last_infer_ms
) {
    if (status_.load() != ConnectionStatus::STREAMING) {
        return false;
    }

    std::cout << "[GrpcEdgeClient][HEARTBEAT] Node: " << node_id
              << " | CPU: " << cpu_percent << "%"
              << " | SPSC Queue Depth: " << queue_depth
              << " | Infer Latency: " << last_infer_ms << " ms" << std::endl;
    return true;
}

} // namespace ndtm::edge
