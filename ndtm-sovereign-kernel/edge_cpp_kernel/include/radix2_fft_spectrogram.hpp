#pragma once

#include <vector>
#include <complex>
#include <cstdint>
#include <span>

namespace ndtm::edge {

using Complex = std::complex<float>;

struct SpectrogramResult {
    float peak_frequency_hz{0.0f};
    float total_power{0.0f};
    float spectral_entropy{0.0f};
    float mel_energies[16]{0.0f};
};

class Radix2FftAnalyzer {
public:
    explicit Radix2FftAnalyzer(size_t window_size = 4096, float sample_rate_hz = 16000.0f);

    // In-place Bit-Reversal Permutation & Cooley-Tukey Radix-2 FFT
    void compute_fft(std::span<Complex> data);

    // Full audio window pipeline: Hann Window -> FFT -> Power Spectrum -> 16 Mel Filterbanks
    SpectrogramResult analyze(std::span<const float> pcm_samples);

    static float hz_to_mel(float hz) noexcept;
    static float mel_to_hz(float mel) noexcept;

private:
    void init_mel_filterbank();

    size_t window_size_;
    float sample_rate_hz_;
    std::vector<float> hann_window_;
    std::vector<size_t> bit_reversed_indices_;
    std::vector<std::vector<float>> mel_filters_; // 16 filters x (window_size / 2 + 1)
};

} // namespace ndtm::edge
