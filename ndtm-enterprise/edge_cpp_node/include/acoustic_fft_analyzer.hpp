#pragma once

#include <vector>
#include <complex>
#include <cstddef>

namespace ndtm::edge {

struct SpectralAnalysisResult {
    std::vector<float> mel_bands;         // 16 Mel-scale energy bins
    double spectral_entropy{0.0};         // Normalized Shannon spectral entropy [0, 1]
    double bearing_fault_harmonic{0.0};   // High-frequency harmonic distortion ratio
    double peak_frequency_hz{0.0};        // Dominant frequency bin
    double total_power{0.0};              // Total integrated spectral energy
    bool acoustic_anomaly_flag{false};    // Pre-classifier threshold flag
};

class AcousticFFTAnalyzer {
public:
    explicit AcousticFFTAnalyzer(size_t window_size = 1024, double sample_rate_hz = 16000.0);
    ~AcousticFFTAnalyzer() = default;

    /**
     * @brief Performs full Cooley-Tukey Radix-2 FFT, Mel-scale projection, and harmonic decomposition.
     * @param raw_samples Time-domain acoustic/vibration signal samples.
     * @return SpectralAnalysisResult containing calculated acoustic features.
     */
    SpectralAnalysisResult analyze(const std::vector<float>& raw_samples);

    [[nodiscard]] size_t window_size() const noexcept { return window_size_; }
    [[nodiscard]] double sample_rate() const noexcept { return sample_rate_hz_; }

private:
    void precompute_hann_window();
    void precompute_mel_filterbank();

    // In-place Bit-Reversal and Radix-2 Cooley-Tukey FFT
    void cooley_tukey_fft(std::vector<std::complex<double>>& data);

    size_t window_size_;
    double sample_rate_hz_;
    std::vector<double> hann_window_;
    std::vector<std::vector<double>> mel_filters_; // [16][window_size_ / 2]
    static constexpr size_t NUM_MEL_BANDS = 16;
};

} // namespace ndtm::edge
