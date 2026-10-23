#pragma once

#include <cstdint>
#include <cstddef>
#include <vector>
#include <span>

namespace ndtm::edge {

struct OpticsAnalysisResult {
    float laplacian_variance{0.0f};
    bool is_sharp{false};
    bool is_polyglot_detected{false};
    size_t sanitized_size_bytes{0};
};

class LaplacianSimdOptics {
public:
    explicit LaplacianSimdOptics(float min_variance_threshold = 85.0f);

    // Computes discrete 2D Laplacian variance on 8-bit grayscale image
    float compute_laplacian_variance(std::span<const uint8_t> grayscale_pixels, size_t width, size_t height);

    // Strips EXIF metadata blocks (APP1 0xFFE1) from raw JPEG stream
    std::vector<uint8_t> strip_jpeg_exif(std::span<const uint8_t> raw_jpeg_bytes);

    // Detects executable headers and polyglot smuggling in image payload
    bool detect_polyglot_exploit(std::span<const uint8_t> raw_bytes);

    // Full optics validation pipeline
    OpticsAnalysisResult process_image(
        std::span<const uint8_t> raw_jpeg_bytes,
        std::span<const uint8_t> grayscale_pixels,
        size_t width,
        size_t height
    );

private:
    float min_variance_threshold_;
};

} // namespace ndtm::edge
