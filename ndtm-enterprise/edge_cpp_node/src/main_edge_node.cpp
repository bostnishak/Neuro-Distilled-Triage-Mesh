#include <iostream>
#include <vector>
#include <thread>
#include <chrono>
#include <csignal>
#include <atomic>
#include <cmath>
#include <random>

#include "lock_free_ring_buffer.hpp"
#include "acoustic_fft_analyzer.hpp"
#include "onnx_edge_runner.hpp"
#include "grpc_edge_client.hpp"

using namespace ndtm::edge;

static constexpr double PI = 3.14159265358979323846;
static std::atomic<bool> g_running{true};

void signal_handler(int signum) {
    std::cout << "\n[EdgeNode] Received shutdown signal (" << signum << "). Stopping worker threads..." << std::endl;
    g_running.store(false);
}

int main(int argc, char* argv[]) {
    std::signal(SIGINT, signal_handler);
    std::signal(SIGTERM, signal_handler);

    const std::string node_id = (argc > 1) ? argv[1] : "EDGE_NODE_ISTANBUL_01";
    const std::string gateway_url = (argc > 2) ? argv[2] : "backend:50051";

    std::cout << "========================================================\n"
              << " NDTM v2.0 C++20 High-Performance Sovereign Edge Node   \n"
              << " Node ID: " << node_id << " | Gateway: " << gateway_url << "\n"
              << " Lock-Free SPSC Ring Buffer + Radix-2 FFT + INT8 ONNX   \n"
              << "========================================================" << std::endl;

    // 1. Initialize SPSC Lock-Free Ring Buffer (Capacity 1024 frames)
    static constexpr size_t BUFFER_CAPACITY = 1024;
    LockFreeRingBuffer<std::vector<float>, BUFFER_CAPACITY> telemetry_ring_buffer;

    // 2. Initialize Processing Engines
    static constexpr size_t WINDOW_SIZE = 1024;
    static constexpr double SAMPLE_RATE_HZ = 16000.0;
    AcousticFFTAnalyzer fft_analyzer(WINDOW_SIZE, SAMPLE_RATE_HZ);
    OnnxEdgeRunner onnx_runner("models/edge_acoustic_int8.onnx");
    onnx_runner.initialize();

    GrpcEdgeClient grpc_client(gateway_url);
    grpc_client.connect();

    // 3. Thread A: High-Frequency Sensor Producer (Simulating 16kHz Audio/Vibration Transducer)
    std::thread producer_thread([&]() {
        std::mt19937 rng(1337);
        std::normal_distribution<float> noise_dist(0.0f, 0.05f);
        size_t frame_counter = 0;

        while (g_running.load()) {
            std::vector<float> frame(WINDOW_SIZE);
            const bool inject_harmonic_anomaly = (frame_counter % 20 == 0); // Periodic fault spike

            for (size_t i = 0; i < WINDOW_SIZE; ++i) {
                const double t = static_cast<double>(i) / SAMPLE_RATE_HZ;
                // Baseline 50Hz electrical grid hum + ambient acoustic noise
                float sample = 0.5f * std::sin(2.0 * PI * 50.0 * t) + noise_dist(rng);

                if (inject_harmonic_anomaly) {
                    // Inject 4200 Hz high-frequency bearing degradation screech
                    sample += 0.8f * std::sin(2.0 * PI * 4200.0 * t);
                }
                frame[i] = sample;
            }

            // Push to SPSC ring buffer without mutex locks
            if (!telemetry_ring_buffer.push(std::move(frame))) {
                // Buffer full backpressure
                std::this_thread::yield();
            }

            frame_counter++;
            std::this_thread::sleep_for(std::chrono::milliseconds(30));
        }
    });

    // 4. Thread B: Consumer Thread (Cooley-Tukey FFT + ONNX Inference + gRPC Dispatch)
    std::thread consumer_thread([&]() {
        std::vector<float> raw_frame;
        size_t processed_frames = 0;

        while (g_running.load()) {
            if (telemetry_ring_buffer.pop(raw_frame)) {
                // 1. Spectral decomposition
                const SpectralAnalysisResult fft_result = fft_analyzer.analyze(raw_frame);

                // 2. Prepare 18-D feature vector for ONNX edge classification
                std::vector<float> edge_features = fft_result.mel_bands;
                edge_features.push_back(static_cast<float>(fft_result.spectral_entropy));
                edge_features.push_back(static_cast<float>(fft_result.bearing_fault_harmonic));

                // 3. Local INT8 inference
                const EdgeInferenceResult infer_result = onnx_runner.predict(edge_features);

                // 4. Dispatch over gRPC stream if anomaly detected or periodic checkpoint
                const bool should_stream = infer_result.requires_immediate_dispatch ||
                                           (processed_frames % 50 == 0);

                if (should_stream) {
                    EdgeTelemetryPacket packet;
                    packet.node_id = node_id;
                    packet.timestamp_unix_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
                        std::chrono::system_clock::now().time_since_epoch()
                    ).count();
                    packet.sample_rate_hz = SAMPLE_RATE_HZ;
                    packet.mel_bands = fft_result.mel_bands;
                    packet.spectral_entropy = fft_result.spectral_entropy;
                    packet.bearing_fault_harmonic = fft_result.bearing_fault_harmonic;
                    packet.anomaly_score = infer_result.anomaly_score;
                    packet.is_critical_alert = infer_result.requires_immediate_dispatch;

                    grpc_client.send_sensor_frame(packet);
                }

                processed_frames++;
            } else {
                std::this_thread::sleep_for(std::chrono::milliseconds(5));
            }
        }
    });

    // 5. Thread C: Heartbeat & Health Monitoring
    std::thread heartbeat_thread([&]() {
        while (g_running.load()) {
            std::this_thread::sleep_for(std::chrono::seconds(5));
            if (!g_running.load()) break;

            grpc_client.send_heartbeat(
                node_id,
                14.2, // Simulated CPU load
                static_cast<uint32_t>(telemetry_ring_buffer.size()),
                0.85  // Inference latency in ms
            );
        }
    });

    std::cout << "[EdgeNode] All 3 edge worker threads active and running." << std::endl;

    // Join threads on shutdown
    producer_thread.join();
    consumer_thread.join();
    heartbeat_thread.join();

    grpc_client.disconnect();
    std::cout << "[EdgeNode] Clean shutdown complete. Exiting." << std::endl;
    return 0;
}
