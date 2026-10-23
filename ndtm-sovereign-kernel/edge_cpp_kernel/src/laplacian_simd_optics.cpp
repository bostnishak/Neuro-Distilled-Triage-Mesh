#include "laplacian_simd_optics.hpp"

#include <cmath>
#include <cstring>
#include <string_view>

namespace ndtm::edge {

LaplacianSimdOptics::LaplacianSimdOptics(float min_variance_threshold)
    : min_variance_threshold_(min_variance_threshold) {}

float LaplacianSimdOptics::compute_laplacian_variance(
    std::span<const uint8_t> grayscale_pixels,
    size_t width,
    size_t height
) {
    if (width < 3 || height < 3 || grayscale_pixels.size() < width * height) {
        return 0.0f;
    }

    double sum = 0.0;
    double sum_sq = 0.0;
    const size_t count = (width - 2) * (height - 2);

    for (size_t y = 1; y < height - 1; ++y) {
        const size_t row_prev = (y - 1) * width;
        const size_t row_curr = y * width;
        const size_t row_next = (y + 1) * width;

        for (size_t x = 1; x < width - 1; ++x) {
            // Discrete 2D Laplacian: L = top + bottom + left + right - 4 * center
            const int32_t top    = grayscale_pixels[row_prev + x];
            const int32_t bottom = grayscale_pixels[row_next + x];
            const int32_t left   = grayscale_pixels[row_curr + x - 1];
            const int32_t right  = grayscale_pixels[row_curr + x + 1];
            const int32_t center = grayscale_pixels[row_curr + x];

            const int32_t lap = top + bottom + left + right - (4 * center);
            const double lap_d = static_cast<double>(lap);

            sum += lap_d;
            sum_sq += lap_d * lap_d;
        }
    }

    const double mean = sum / static_cast<double>(count);
    const double variance = (sum_sq / static_cast<double>(count)) - (mean * mean);

    return static_cast<float>(variance >= 0.0 ? variance : 0.0);
}

std::vector<uint8_t> LaplacianSimdOptics::strip_jpeg_exif(std::span<const uint8_t> raw_jpeg_bytes) {
    if (raw_jpeg_bytes.size() < 4) {
        return {raw_jpeg_bytes.begin(), raw_jpeg_bytes.end()};
    }

    // Check JPEG SOI (0xFF 0xD8)
    if (raw_jpeg_bytes[0] != 0xFF || raw_jpeg_bytes[1] != 0xD8) {
        return {raw_jpeg_bytes.begin(), raw_jpeg_bytes.end()};
    }

    std::vector<uint8_t> sanitized;
    sanitized.reserve(raw_jpeg_bytes.size());

    sanitized.push_back(0xFF);
    sanitized.push_back(0xD8);

    size_t i = 2;
    const size_t total_len = raw_jpeg_bytes.size();

    while (i < total_len - 1) {
        if (raw_jpeg_bytes[i] != 0xFF) {
            sanitized.push_back(raw_jpeg_bytes[i++]);
            continue;
        }

        const uint8_t marker = raw_jpeg_bytes[i + 1];

        // Standalone markers: RST0..RST7, SOI, EOI, TEM
        if (marker == 0xD8 || marker == 0xD9 || (marker >= 0xD0 && marker <= 0xD7) || marker == 0x01) {
            sanitized.push_back(0xFF);
            sanitized.push_back(marker);
            i += 2;
            continue;
        }

        // Start of Scan (SOS): Rest of the stream is compressed image payload
        if (marker == 0xDA) {
            sanitized.insert(sanitized.end(), raw_jpeg_bytes.begin() + static_cast<ptrdiff_t>(i), raw_jpeg_bytes.end());
            break;
        }

        // Variable length marker: read segment length (big-endian 16-bit)
        if (i + 3 >= total_len) {
            break;
        }

        const uint16_t segment_len = (static_cast<uint16_t>(raw_jpeg_bytes[i + 2]) << 8) | static_cast<uint16_t>(raw_jpeg_bytes[i + 3]);

        if (marker == 0xE1) {
            // APP1 Marker (EXIF / XMP metadata) -> Strip this segment completely!
            i += 2 + segment_len;
        } else {
            // Keep all other markers (SOF, DHT, DQT, APP0 JFIF, etc.)
            const size_t end_idx = std::min(total_len, i + 2 + segment_len);
            sanitized.insert(sanitized.end(), raw_jpeg_bytes.begin() + static_cast<ptrdiff_t>(i), raw_jpeg_bytes.begin() + static_cast<ptrdiff_t>(end_idx));
            i = end_idx;
        }
    }

    return sanitized;
}

bool LaplacianSimdOptics::detect_polyglot_exploit(std::span<const uint8_t> raw_bytes) {
    if (raw_bytes.size() < 2) {
        return false;
    }

    // 1. Windows PE / DOS Executable Header ('MZ' = 0x4D 0x5A)
    if (raw_bytes[0] == 0x4D && raw_bytes[1] == 0x5A) {
        return true;
    }

    // 2. Linux ELF Header (0x7F 'E' 'L' 'F')
    if (raw_bytes.size() >= 4 && raw_bytes[0] == 0x7F && raw_bytes[1] == 'E' && raw_bytes[2] == 'L' && raw_bytes[3] == 'F') {
        return true;
    }

    // 3. Zip / JAR / APK Polyglot Header (0x50 0x4B 0x03 0x04)
    if (raw_bytes.size() >= 4 && raw_bytes[0] == 0x50 && raw_bytes[1] == 0x4B && raw_bytes[2] == 0x03 && raw_bytes[3] == 0x04) {
        return true;
    }

    // 4. HTML/PHP/Script Smuggling Signature Inspection
    const std::string_view payload(reinterpret_cast<const char*>(raw_bytes.data()), raw_bytes.size());
    if (payload.find("<script") != std::string_view::npos ||
        payload.find("<?php") != std::string_view::npos ||
        payload.find("eval(") != std::string_view::npos) {
        return true;
    }

    return false;
}

OpticsAnalysisResult LaplacianSimdOptics::process_image(
    std::span<const uint8_t> raw_jpeg_bytes,
    std::span<const uint8_t> grayscale_pixels,
    size_t width,
    size_t height
) {
    OpticsAnalysisResult res{};

    // 1. Check for polyglot smuggling
    res.is_polyglot_detected = detect_polyglot_exploit(raw_jpeg_bytes);
    if (res.is_polyglot_detected) {
        res.is_sharp = false;
        return res;
    }

    // 2. Compute Laplacian variance
    res.laplacian_variance = compute_laplacian_variance(grayscale_pixels, width, height);
    res.is_sharp = (res.laplacian_variance >= min_variance_threshold_);

    // 3. Strip EXIF
    const auto sanitized = strip_jpeg_exif(raw_jpeg_bytes);
    res.sanitized_size_bytes = sanitized.size();

    return res;
}

} // namespace ndtm::edge
