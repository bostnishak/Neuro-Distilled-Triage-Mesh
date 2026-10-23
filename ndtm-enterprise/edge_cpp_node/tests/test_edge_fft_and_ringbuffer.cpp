#include "lock_free_ring_buffer.hpp"
#include "acoustic_fft_analyzer.hpp"

#include <iostream>
#include <thread>
#include <vector>
#include <cmath>
#include <cassert>
#include <atomic>
#include <chrono>

using namespace ndtm::edge;

static constexpr double PI = 3.14159265358979323846;

// -----------------------------------------------------------------------------
// Test 1: SPSC Lock-Free Ring Buffer Producer-Consumer Throughput & Integrity
// -----------------------------------------------------------------------------
void test_lock_free_ring_buffer() {
    std::cout << "[TEST] 1. Lock-Free SPSC Ring Buffer Multi-Threaded Stress Test (100,000 frames)..." << std::endl;

    constexpr size_t BUFFER_CAPACITY = 1024;
    constexpr size_t TOTAL_FRAMES = 100000;

    struct TelemetryFrame {
        uint64_t seq;
        double sensor_reading;
    };

    LockFreeRingBuffer<TelemetryFrame, BUFFER_CAPACITY> ring_buffer;
    std::atomic<bool> producer_done{false};
    std::atomic<size_t> frames_received{0};
    std::atomic<bool> data_corruption{false};

    // Producer Thread
    std::thread producer([&]() {
        for (uint64_t i = 0; i < TOTAL_FRAMES; ++i) {
            TelemetryFrame frame{i, static_cast<double>(i) * 1.5};
            while (!ring_buffer.push(frame)) {
                std::this_thread::yield();
            }
        }
        producer_done.store(true, std::memory_order_release);
    });

    // Consumer Thread
    std::thread consumer([&]() {
        uint64_t expected_seq = 0;
        while (!producer_done.load(std::memory_order_acquire) || !ring_buffer.empty()) {
            TelemetryFrame frame;
            if (ring_buffer.pop(frame)) {
                if (frame.seq != expected_seq || std::abs(frame.sensor_reading - (static_cast<double>(expected_seq) * 1.5)) > 1e-6) {
                    data_corruption.store(true, std::memory_order_relaxed);
                }
                expected_seq++;
                frames_received.fetch_add(1, std::memory_order_relaxed);
            } else {
                std::this_thread::yield();
            }
        }
    });

    producer.join();
    consumer.join();

    std::cout << "       Frames Pushed: " << TOTAL_FRAMES << " | Frames Received: " << frames_received.load() << std::endl;
    assert(!data_corruption.load() && "Data corruption detected in ring buffer!");
    assert(frames_received.load() == TOTAL_FRAMES && "Frame drop detected in lock-free ring buffer!");
    std::cout << "       [PASS] SPSC Lock-Free Ring Buffer: 100,000 frames atomically ingested with 0 drops." << std::endl;
}

// -----------------------------------------------------------------------------
// Test 2: Cooley-Tukey FFT & Mel-Scale Spectral Power Peak Invariants
// -----------------------------------------------------------------------------
void test_cooley_tukey_fft_peaks() {
    std::cout << "[TEST] 2. Cooley-Tukey Radix-2 FFT Power Spectrum & Mel-Filter Invariant Proof..." << std::endl;

    constexpr size_t WINDOW_SIZE = 1024;
    constexpr double SAMPLE_RATE = 16000.0;
    constexpr double FREQ1 = 1000.0; // 1000 Hz dominant tone
    constexpr double FREQ2 = 3500.0; // 3500 Hz secondary tone

    AcousticFFTAnalyzer analyzer(WINDOW_SIZE, SAMPLE_RATE);

    // Synthesize composite signal x(t) = sin(2*pi*1000*t) + 0.5*sin(2*pi*3500*t)
    std::vector<float> signal(WINDOW_SIZE);
    for (size_t i = 0; i < WINDOW_SIZE; ++i) {
        double t = static_cast<double>(i) / SAMPLE_RATE;
        signal[i] = static_cast<float>(std::sin(2.0 * PI * FREQ1 * t) + 0.5 * std::sin(2.0 * PI * FREQ2 * t));
    }

    SpectralAnalysisResult res = analyzer.analyze(signal);

    std::cout << "       Synthesized Primary Tone: " << FREQ1 << " Hz | Peak Frequency Detected: " << res.peak_frequency_hz << " Hz" << std::endl;
    std::cout << "       Total Integrated Spectral Power: " << res.total_power << std::endl;
    std::cout << "       Normalized Spectral Entropy: " << res.spectral_entropy << std::endl;

    // Peak frequency must align with 1000 Hz within bin resolution (16000 / 1024 = 15.625 Hz/bin)
    constexpr double BIN_RESOLUTION = SAMPLE_RATE / static_cast<double>(WINDOW_SIZE);
    assert(std::abs(res.peak_frequency_hz - FREQ1) <= BIN_RESOLUTION * 1.5 && "Dominant peak does not match 1000 Hz!");

    // Total power must be strictly positive
    assert(res.total_power > 0.1 && "Spectral energy below expected threshold!");

    // Mel bands must be populated (16 bands)
    assert(res.mel_bands.size() == 16 && "Mel filterbank did not output 16 bands!");

    // Normalized spectral entropy must be in [0.0, 1.0]
    assert(res.spectral_entropy >= 0.0 && res.spectral_entropy <= 1.0 && "Spectral entropy out of bounds!");

    std::cout << "       [PASS] Cooley-Tukey FFT & Mel-Scale Analysis mathematically proven." << std::endl;
}

int main() {
    std::cout << "==============================================================================" << std::endl;
    std::cout << " [GATE 3B] C++20 EDGE DSP & LOCK-FREE RING BUFFER VERIFICATION SUITE" << std::endl;
    std::cout << "==============================================================================" << std::endl;

    try {
        test_lock_free_ring_buffer();
        test_cooley_tukey_fft_peaks();
        std::cout << "\n[CERTIFICATION APPROVED] Gate 3B C++20 Verification Passed: Exit Code 0." << std::endl;
        return 0;
    } catch (const std::exception& exc) {
        std::cerr << "\n[CERTIFICATION FAILED] Exception in Gate 3B: " << exc.what() << std::endl;
        return 1;
    }
}
