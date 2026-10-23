#include "radix2_fft_spectrogram.hpp"

#include <cmath>
#include <algorithm>
#include <numbers>

namespace ndtm::edge {

Radix2FftAnalyzer::Radix2FftAnalyzer(size_t window_size, float sample_rate_hz)
    : window_size_(window_size),
      sample_rate_hz_(sample_rate_hz),
      hann_window_(window_size),
      bit_reversed_indices_(window_size) {
    
    // 1. Precompute Hann Window
    for (size_t n = 0; n < window_size_; ++n) {
        hann_window_[n] = 0.5f * (1.0f - std::cos(2.0f * std::numbers::pi_v<float> * static_cast<float>(n) / static_cast<float>(window_size_ - 1)));
    }

    // 2. Precompute Bit-Reversal Table
    const size_t num_bits = static_cast<size_t>(std::log2(window_size_));
    for (size_t i = 0; i < window_size_; ++i) {
        size_t reversed = 0;
        for (size_t b = 0; b < num_bits; ++b) {
            if ((i >> b) & 1) {
                reversed |= (1ULL << (num_bits - 1 - b));
            }
        }
        bit_reversed_indices_[i] = reversed;
    }

    // 3. Initialize 16 Mel Filterbanks
    init_mel_filterbank();
}

float Radix2FftAnalyzer::hz_to_mel(float hz) noexcept {
    return 2595.0f * std::log10(1.0f + hz / 700.0f);
}

float Radix2FftAnalyzer::mel_to_hz(float mel) noexcept {
    return 700.0f * (std::pow(10.0f, mel / 2595.0f) - 1.0f);
}

void Radix2FftAnalyzer::init_mel_filterbank() {
    constexpr size_t num_filters = 16;
    const size_t num_bins = (window_size_ / 2) + 1;
    mel_filters_.assign(num_filters, std::vector<float>(num_bins, 0.0f));

    const float min_mel = hz_to_mel(20.0f);
    const float max_mel = hz_to_mel(sample_rate_hz_ / 2.0f);
    const float mel_step = (max_mel - min_mel) / static_cast<float>(num_filters + 1);

    std::vector<float> mel_points(num_filters + 2);
    std::vector<size_t> bin_indices(num_filters + 2);

    for (size_t i = 0; i < num_filters + 2; ++i) {
        mel_points[i] = min_mel + static_cast<float>(i) * mel_step;
        const float hz = mel_to_hz(mel_points[i]);
        bin_indices[i] = std::min(num_bins - 1, static_cast<size_t>(std::floor((window_size_ + 1) * hz / sample_rate_hz_)));
    }

    for (size_t m = 1; m <= num_filters; ++m) {
        const size_t left = bin_indices[m - 1];
        const size_t center = bin_indices[m];
        const size_t right = bin_indices[m + 1];

        for (size_t k = left; k < center; ++k) {
            if (center != left) {
                mel_filters_[m - 1][k] = static_cast<float>(k - left) / static_cast<float>(center - left);
            }
        }
        for (size_t k = center; k <= right; ++k) {
            if (right != center) {
                mel_filters_[m - 1][k] = static_cast<float>(right - k) / static_cast<float>(right - center);
            }
        }
    }
}

void Radix2FftAnalyzer::compute_fft(std::span<Complex> data) {
    const size_t n = data.size();

    // In-place Bit-Reversal Permutation
    for (size_t i = 0; i < n; ++i) {
        const size_t j = bit_reversed_indices_[i];
        if (i < j) {
            std::swap(data[i], data[j]);
        }
    }

    // Cooley-Tukey Radix-2 Butterfly Steps
    for (size_t len = 2; len <= n; len <<= 1) {
        const float angle = -2.0f * std::numbers::pi_v<float> / static_cast<float>(len);
        const Complex wlen(std::cos(angle), std::sin(angle));

        for (size_t i = 0; i < n; i += len) {
            Complex w(1.0f, 0.0f);
            for (size_t j = 0; j < len / 2; ++j) {
                const Complex u = data[i + j];
                const Complex v = data[i + j + len / 2] * w;
                data[i + j] = u + v;
                data[i + j + len / 2] = u - v;
                w *= wlen;
            }
        }
    }
}

SpectrogramResult Radix2FftAnalyzer::analyze(std::span<const float> pcm_samples) {
    SpectrogramResult result{};

    std::vector<Complex> buffer(window_size_, Complex(0.0f, 0.0f));
    const size_t copy_len = std::min(pcm_samples.size(), window_size_);

    for (size_t i = 0; i < copy_len; ++i) {
        buffer[i] = Complex(pcm_samples[i] * hann_window_[i], 0.0f);
    }

    compute_fft(buffer);

    const size_t num_bins = (window_size_ / 2) + 1;
    std::vector<float> power_spectrum(num_bins, 0.0f);

    float max_power = -1.0f;
    size_t peak_bin = 0;

    for (size_t k = 0; k < num_bins; ++k) {
        const float magnitude = std::abs(buffer[k]);
        const float power = (magnitude * magnitude) / static_cast<float>(window_size_);
        power_spectrum[k] = power;
        result.total_power += power;

        if (power > max_power) {
            max_power = power;
            peak_bin = k;
        }
    }

    result.peak_frequency_hz = static_cast<float>(peak_bin) * sample_rate_hz_ / static_cast<float>(window_size_);

    // Compute 16 Mel Filterbank Energies
    float mel_sum = 0.0f;
    for (size_t m = 0; m < 16; ++m) {
        float energy = 0.0f;
        for (size_t k = 0; k < num_bins; ++k) {
            energy += power_spectrum[k] * mel_filters_[m][k];
        }
        result.mel_energies[m] = energy;
        mel_sum += energy;
    }

    // Compute Normalized Spectral Anomaly Entropy
    if (mel_sum > 1e-9f) {
        float entropy = 0.0f;
        for (size_t m = 0; m < 16; ++m) {
            const float p = result.mel_energies[m] / mel_sum;
            if (p > 1e-9f) {
                entropy -= p * std::log(p);
            }
        }
        result.spectral_entropy = entropy / std::log(16.0f);
    } else {
        result.spectral_entropy = 0.0f;
    }

    return result;
}

} // namespace ndtm::edge
