#pragma once

#include <string>
#include <vector>
#include <memory>

namespace ndtm::edge {

struct EdgeInferenceResult {
    double anomaly_score{0.0};
    std::string classified_fault{"NORMAL"};
    bool requires_immediate_dispatch{false};
    double inference_latency_us{0.0};
};

class OnnxEdgeRunner {
public:
    explicit OnnxEdgeRunner(const std::string& model_path = "models/edge_acoustic_int8.onnx");
    ~OnnxEdgeRunner();

    bool initialize();

    /**
     * @brief Runs edge inference on the 18-dimensional feature vector.
     * Features: [16 Mel Bands, Spectral Entropy, Bearing Fault Harmonic]
     */
    EdgeInferenceResult predict(const std::vector<float>& features);

    [[nodiscard]] bool is_initialized() const noexcept { return is_initialized_; }
    [[nodiscard]] const std::string& model_path() const noexcept { return model_path_; }

private:
    std::string model_path_;
    bool is_initialized_{false};

    // Forward pass using deterministic calibrated quantized weights (18 -> 32 -> 4)
    EdgeInferenceResult execute_embedded_quantized_inference(const std::vector<float>& features);
};

} // namespace ndtm::edge
