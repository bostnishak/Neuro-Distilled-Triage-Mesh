#include "grpc_telemetry_bridge.hpp"

#include <iostream>
#include <chrono>
#include <thread>
#include <atomic>
#include <csignal>
#include <cstdlib>
#include <cmath>
#include <numbers>

namespace {
std::atomic<bool> g_running{true};

void signal_handler(int signum) {
    std::cout << "\n[NDTM Edge Daemon] Received termination signal (" << signum << "). Shutting down..." << std::endl;
    g_running.store(false);
}
}

int main() {
    std::signal(SIGINT, signal_handler);
    std::signal(SIGTERM, signal_handler);

    const char* shm_name_env = std::getenv("SHM_ARENA_NAME");
    const std::string arena_name = (shm_name_env && shm_name_env[0] != '\0') ? shm_name_env : "/ndtm_tensor_arena";

    std::cout << "================================================================================" << std::endl;
    std::cout << " NDTM-9000 C++20 ZERO-COPY EDGE DAEMON & POSIX SHM IPC BRIDGE                  " << std::endl;
    std::cout << "================================================================================" << std::endl;
    std::cout << "POSIX Shared Memory Segment : " << arena_name << std::endl;
    std::cout << "Sampling Rate               : 16000 Hz | Window: 4096 Samples" << std::endl;
    std::cout << "Lock-Free SPSC Ring Buffer  : 65,536 Frame Capacity (Zero Malloc)" << std::endl;
    std::cout << "--------------------------------------------------------------------------------" << std::endl;

    ndtm::edge::GrpcTelemetryBridge bridge(arena_name);
    if (!bridge.initialize()) {
        std::cerr << "[FATAL] Failed to create or attach to Shared Memory Arena: " << arena_name << std::endl;
        return 1;
    }

    std::cout << "[+] Shared Memory Arena mapped successfully (" << bridge.get_arena().get_total_slots() << " slots @ 1MB)." << std::endl;

    // Background worker thread: Ingests synthetic acoustic vibration telemetry (1000 Hz tone + noise)
    std::thread telemetry_worker([&bridge]() {
        uint64_t frame_seq = 0;
        constexpr size_t window_size = 4096;
        std::vector<float> pcm_frame(window_size);

        while (g_running.load(std::memory_order_relaxed)) {
            const auto now_ns = static_cast<uint64_t>(
                std::chrono::duration_cast<std::chrono::nanoseconds>(
                    std::chrono::system_clock::now().time_since_epoch()
                ).count()
            );

            // Generate synthetic 1000 Hz transformer humming tone
            for (size_t i = 0; i < window_size; ++i) {
                const float t = static_cast<float>(i) / 16000.0f;
                pcm_frame[i] = 0.8f * std::sin(2.0f * std::numbers::pi_v<float> * 1000.0f * t);
            }

            bridge.ingest_acoustic_stream(now_ns, "DEVICE_ISTANBUL_MASLAK_SUB01", pcm_frame);
            bridge.flush_ring_to_shm();

            ++frame_seq;
            std::this_thread::sleep_for(std::chrono::milliseconds(20)); // ~50 fps
        }
    });

    // Main status reporting loop
    auto last_report = std::chrono::steady_clock::now();
    while (g_running.load(std::memory_order_relaxed)) {
        std::this_thread::sleep_for(std::chrono::milliseconds(500));

        const auto now = std::chrono::steady_clock::now();
        if (std::chrono::duration_cast<std::chrono::seconds>(now - last_report).count() >= 5) {
            last_report = now;
            std::cout << "[STATUS] SHM Write Sequence: " << bridge.get_arena().get_write_seq()
                      << " | Ring Buffer Backlog: " << bridge.get_ring().size() << " frames" << std::endl;
        }
    }

    if (telemetry_worker.joinable()) {
        telemetry_worker.join();
    }

    bridge.shutdown();
    std::cout << "[+] NDTM Edge Daemon terminated cleanly." << std::endl;
    return 0;
}
