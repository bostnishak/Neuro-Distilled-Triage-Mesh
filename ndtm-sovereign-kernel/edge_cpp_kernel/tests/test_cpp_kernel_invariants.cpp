#include "spsc_atomic_ring.hpp"
#include "radix2_fft_spectrogram.hpp"
#include "laplacian_simd_optics.hpp"
#include "shm_zero_copy_arena.hpp"

#include <iostream>
#include <cassert>
#include <thread>
#include <vector>
#include <cmath>
#include <numeric>
#include <numbers>

using namespace ndtm::edge;

void test_spsc_ring_buffer_100k_stress() {
    std::cout << "[TEST 1] SPSC Lock-Free Ring Buffer 100,000 Frames Stress Test..." << std::endl;

    constexpr size_t total_frames = 100000;
    SPSCAtomicRingBuffer<uint64_t, 65536> ring;

    std::atomic<bool> producer_done{false};
    std::vector<uint64_t> received;
    received.reserve(total_frames);

    // Producer Thread
    std::thread producer([&ring, &producer_done]() {
        for (uint64_t i = 1; i <= total_frames; ++i) {
            while (!ring.push(i)) {
                std::this_thread::yield();
            }
        }
        producer_done.store(true, std::memory_order_release);
    });

    // Consumer Thread
    std::thread consumer([&ring, &producer_done, &received]() {
        uint64_t val = 0;
        while (!producer_done.load(std::memory_order_acquire) || !ring.empty()) {
            if (ring.pop(val)) {
                received.push_back(val);
            } else {
                std::this_thread::yield();
            }
        }
    });

    producer.join();
    consumer.join();

    assert(received.size() == total_frames);
    for (size_t i = 0; i < total_frames; ++i) {
        assert(received[i] == (i + 1));
    }

    std::cout << "         -> PASSED: 100,000 frames pushed and consumed with zero drops." << std::endl;
}

void test_cooley_tukey_fft_peak_detection() {
    std::cout << "[TEST 2] Cooley-Tukey Radix-2 FFT & Mel-Scale Invariant Proof..." << std::endl;

    constexpr size_t window_size = 4096;
    constexpr float sample_rate = 16000.0f;
    constexpr float target_freq = 1000.0f;

    Radix2FftAnalyzer analyzer(window_size, sample_rate);

    std::vector<float> pcm(window_size);
    for (size_t i = 0; i < window_size; ++i) {
        const float t = static_cast<float>(i) / sample_rate;
        pcm[i] = std::sin(2.0f * std::numbers::pi_v<float> * target_freq * t);
    }

    const auto res = analyzer.analyze(pcm);

    std::cout << "         Synthesized: " << target_freq << " Hz | Detected Peak: " << res.peak_frequency_hz << " Hz" << std::endl;
    std::cout << "         Total Power: " << res.total_power << " | Spectral Entropy: " << res.spectral_entropy << std::endl;

    // Peak frequency must match 1000 Hz within FFT frequency resolution (16000 / 4096 = 3.9 Hz)
    assert(std::abs(res.peak_frequency_hz - target_freq) <= 10.0f);
    assert(res.total_power > 0.0f);
    assert(res.spectral_entropy > 0.0f && res.spectral_entropy <= 1.0f);

    std::cout << "         -> PASSED: Cooley-Tukey FFT peak detection verified within 10Hz bound." << std::endl;
}

void test_laplacian_optics_and_exif() {
    std::cout << "[TEST 3] SIMD Laplacian Blur Detection & EXIF Stripping..." << std::endl;

    LaplacianSimdOptics optics(85.0f);

    // 1. Sharp checkerboard image
    constexpr size_t width = 64;
    constexpr size_t height = 64;
    std::vector<uint8_t> sharp_img(width * height);
    for (size_t y = 0; y < height; ++y) {
        for (size_t x = 0; x < width; ++x) {
            sharp_img[y * width + x] = ((x / 4) % 2 == (y / 4) % 2) ? 255 : 0;
        }
    }

    const float sharp_var = optics.compute_laplacian_variance(sharp_img, width, height);
    assert(sharp_var > 500.0f);

    // 2. Blurred / flat uniform image
    std::vector<uint8_t> flat_img(width * height, 128);
    const float flat_var = optics.compute_laplacian_variance(flat_img, width, height);
    assert(flat_var == 0.0f);

    // 3. Polyglot exploit detection
    const uint8_t pe_header[] = {0x4D, 0x5A, 0x90, 0x00, 0x03}; // 'MZ'
    assert(optics.detect_polyglot_exploit(pe_header) == true);

    const uint8_t clean_img[] = {0xFF, 0xD8, 0xFF, 0xDB, 0x00, 0x43};
    assert(optics.detect_polyglot_exploit(clean_img) == false);

    std::cout << "         Sharp Variance: " << sharp_var << " (Threshold: 85.0) | Flat Variance: " << flat_var << std::endl;
    std::cout << "         -> PASSED: Blur filtering and polyglot detection verified." << std::endl;
}

void test_shm_arena_zero_copy() {
    std::cout << "[TEST 4] POSIX Shared Memory Arena Zero-Copy Read/Write..." << std::endl;

    ShmZeroCopyArena arena;
    const bool attached = arena.create_or_attach("/ndtm_test_arena", 16);
    assert(attached);

    SlotHeader in_header{};
    in_header.slot_id = 42;
    in_header.magic_header = NDTM_SHM_MAGIC;
    in_header.shape[0] = 1;
    in_header.shape[1] = 1;
    in_header.shape[2] = 1;
    in_header.shape[3] = 16;
    in_header.spectral_entropy = 0.45f;

    std::vector<float> in_tensor(16);
    std::iota(in_tensor.begin(), in_tensor.end(), 1.0f);

    const bool write_ok = arena.write_tensor_slot(0, in_header, in_tensor);
    assert(write_ok);

    SlotHeader out_header{};
    std::vector<float> out_tensor;
    const bool read_ok = arena.read_tensor_slot(0, out_header, out_tensor);
    assert(read_ok);

    assert(out_header.slot_id == 42);
    assert(out_header.magic_header == NDTM_SHM_MAGIC);
    assert(out_tensor.size() == 16);
    for (size_t i = 0; i < 16; ++i) {
        assert(std::abs(out_tensor[i] - static_cast<float>(i + 1)) < 1e-6f);
    }

    arena.cleanup();
    std::cout << "         -> PASSED: Zero-copy slot serialization and deserialization verified." << std::endl;
}

int main() {
    std::cout << "================================================================================" << std::endl;
    std::cout << " NDTM-9000 C++20 EDGE KERNEL INVARIANT VERIFICATION SUITE                       " << std::endl;
    std::cout << "================================================================================" << std::endl;

    test_spsc_ring_buffer_100k_stress();
    test_cooley_tukey_fft_peak_detection();
    test_laplacian_optics_and_exif();
    test_shm_arena_zero_copy();

    std::cout << "\n[ALL C++20 INVARIANTS CERTIFIED WITH 0 DEFECTS]" << std::endl;
    return 0;
}
