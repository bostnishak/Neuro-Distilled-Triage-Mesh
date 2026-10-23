#include "acoustic_fft_analyzer.hpp"

#include <cmath>
#include <algorithm>
#include <numeric>

namespace ndtm::edge {

static constexpr double PI = 3.14159265358979323846;

AcousticFFTAnalyzer::AcousticFFTAnalyzer(size_t window_size, double sample_rate_hz)
    : window_size_(window_size), sample_rate_hz_(sample_rate_hz) {
    precompute_hann_window();
    precompute_mel_filterbank();
}

void AcousticFFTAnalyzer::precompute_hann_window() {
    hann_window_.resize(window_size_);
    const double n_minus_1 = static_cast<double>(window_size_ - 1);
    for (size_t n = 0; n < window_size_; ++n) {
        hann_window_[n] = 0.5 * (1.0 - std::cos(2.0 * PI * static_cast<double>(n) / n_minus_1));
    }
}

static double hz_to_mel(double hz) {
    return 2595.0 * std::log10(1.0 + hz / 700.0);
}

static double mel_to_hz(double mel) {
    return 700.0 * (std::pow(10.0, mel / 2595.0) - 1.0);
}

void AcousticFFTAnalyzer::precompute_mel_filterbank() {
    const size_t num_fft_bins = window_size_ / 2;
    mel_filters_.assign(NUM_MEL_BANDS, std::vector<double>(num_fft_bins, 0.0));

    const double min_hz = 20.0;
    const double max_hz = sample_rate_hz_ / 2.0; // Nyquist limit

    const double min_mel = hz_to_mel(min_hz);
    const double max_mel = hz_to_mel(max_hz);

    // Linear spacing in Mel domain
    std::vector<double> mel_points(NUM_MEL_BANDS + 2);
    for (size_t i = 0; i < mel_points.size(); ++i) {
        mel_points[i] = min_mel + i * (max_mel - min_mel) / (NUM_MEL_BANDS + 1);
    }

    std::vector<double> hz_points(NUM_MEL_BANDS + 2);
    std::vector<size_t> bin_points(NUM_MEL_BANDS + 2);
    for (size_t i = 0; i < mel_points.size(); ++i) {
        hz_points[i] = mel_to_hz(mel_points[i]);
        bin_points[i] = static_cast<size_t>(std::floor((window_size_ + 1) * hz_points[i] / sample_rate_hz_));
        if (bin_points[i] >= num_fft_bins) {
            bin_points[i] = num_fft_bins - 1;
        }
    }

    // Construct triangular filters
    for (size_t m = 1; m <= NUM_MEL_BANDS; ++m) {
        const size_t f_m_minus = bin_points[m - 1];
        const size_t f_m = bin_points[m];
        const size_t f_m_plus = bin_points[m + 1];

        for (size_t k = f_m_minus; k < f_m; ++k) {
            if (f_m > f_m_minus) {
                mel_filters_[m - 1][k] = static_cast<double>(k - f_m_minus) / (f_m - f_m_minus);
            }
        }
        for (size_t k = f_m; k <= f_m_plus; ++k) {
            if (f_m_plus > f_m && k < num_fft_bins) {
                mel_filters_[m - 1][k] = static_cast<double>(f_m_plus - k) / (f_m_plus - f_m);
            }
        }
    }
}

void AcousticFFTAnalyzer::cooley_tukey_fft(std::vector<std::complex<double>>& data) {
    const size_t n = data.size();
    if (n <= 1) return;

    // In-place Bit-Reversal Permutation
    for (size_t i = 1, j = 0; i < n; ++i) {
        size_t bit = n >> 1;
        for (; j & bit; bit >>= 1) {
            j ^= bit;
        }
        j ^= bit;
        if (i < j) {
            std::swap(data[i], data[j]);
        }
    }

    // Radix-2 Butterfly Computation
    for (size_t len = 2; len <= n; len <<= 1) {
        const double angle = -2.0 * PI / static_cast<double>(len);
        const std::complex<double> wlen(std::cos(angle), std::sin(angle));
        for (size_t i = 0; i < n; i += len) {
            std::complex<double> w(1.0, 0.0);
            for (size_t j = 0; j < len / 2; ++j) {
                const std::complex<double> u = data[i + j];
                const std::complex<double> v = data[i + j + len / 2] * w;
                data[i + j] = u + v;
                data[i + j + len / 2] = u - v;
                w *= wlen;
            }
        }
    }
}

SpectralAnalysisResult AcousticFFTAnalyzer::analyze(const std::vector<float>& raw_samples) {
    SpectralAnalysisResult result;
    result.mel_bands.assign(NUM_MEL_BANDS, 0.0f);

    std::vector<std::complex<double>> complex_signal(window_size_, std::complex<double>(0.0, 0.0));
    const size_t samples_to_copy = std::min(raw_samples.size(), window_size_);

    for (size_t i = 0; i < samples_to_copy; ++i) {
        complex_signal[i] = std::complex<double>(raw_samples[i] * hann_window_[i], 0.0);
    }

    cooley_tukey_fft(complex_signal);

    const size_t num_bins = window_size_ / 2;
    std::vector<double> power_spectrum(num_bins, 0.0);
    double total_power = 0.0;
    double max_power = 0.0;
    size_t peak_bin = 0;

    for (size_t k = 0; k < num_bins; ++k) {
        const double re = complex_signal[k].real();
        const double im = complex_signal[k].imag();
        const double power = (re * re + im * im) / static_cast<double>(window_size_);
        power_spectrum[k] = power;
        total_power += power;
        if (power > max_power) {
            max_power = power;
            peak_bin = k;
        }
    }

    result.total_power = total_power;
    result.peak_frequency_hz = static_cast<double>(peak_bin) * sample_rate_hz_ / static_cast<double>(window_size_);

    // 1. Compute 16 Mel-Scale Energy Bands
    for (size_t m = 0; m < NUM_MEL_BANDS; ++m) {
        double band_energy = 0.0;
        for (size_t k = 0; k < num_bins; ++k) {
            band_energy += power_spectrum[k] * mel_filters_[m][k];
        }
        // Log-energy with epsilon offset
        result.mel_bands[m] = static_cast<float>(std::log(std::max(band_energy, 1e-9)));
    }

    // 2. Compute Normalized Spectral Entropy H(p)
    if (total_power > 1e-9) {
        double entropy = 0.0;
        for (size_t k = 0; k < num_bins; ++k) {
            const double p = power_spectrum[k] / total_power;
            if (p > 1e-12) {
                entropy -= p * std::log(p);
            }
        }
        // Normalize by log(N/2)
        result.spectral_entropy = entropy / std::log(static_cast<double>(num_bins));
    } else {
        result.spectral_entropy = 0.0;
    }

    // 3. Compute High-Frequency Bearing Fault Harmonic Ratio
    // Ratio of high band energy (bands 12..15: typically 3kHz - 8kHz) to low band energy (bands 0..3)
    double low_energy = 0.0;
    double high_energy = 0.0;
    for (size_t i = 0; i < 4; ++i) {
        low_energy += std::exp(result.mel_bands[i]);
    }
    for (size_t i = 12; i < 16; ++i) {
        high_energy += std::exp(result.mel_bands[i]);
    }

    result.bearing_fault_harmonic = (low_energy > 1e-9) ? (high_energy / low_energy) : 0.0;

    // Heuristic anomaly trigger: elevated high-frequency harmonics + high entropy
    if (result.bearing_fault_harmonic > 2.5 || result.spectral_entropy > 0.82) {
        result.acoustic_anomaly_flag = true;
    }

    return result;
}

} // namespace ndtm::edge
