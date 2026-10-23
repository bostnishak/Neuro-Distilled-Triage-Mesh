import React, { useState, useEffect } from "react";
import { apiClient } from "../services/apiClient";
import { wsClient } from "../services/wsClient";
import { RouterInferenceResponse, LiveMetricsSnapshot } from "../types/api";

const PRESET_PROMPTS = [
  {
    label: "Routine Pothole (High Confidence -> ONNX Student)",
    text: "Orta refüj yanında derin bir çukur oluştu. Trafik yavaşlıyor ve araç lastikleri patlama riski altında.",
  },
  {
    label: "Ambiguous Crisis (High Entropy -> Teacher LLM)",
    text: "Garip bir ses geldi, elektrik telleri titriyor ama gaz kokusu da var ne yapacağımızı bilemedik acil gelin.",
  },
  {
    label: "Water Infrastructure (Semantic Cache Candidate)",
    text: "Ana boru patladı, cadde sular altında kaldı. Su basıncı sıfıra düştü acil İSKİ müdahalesi gerekiyor.",
  },
];

export const DistillMeshRouterView: React.FC = () => {
  const [metrics, setMetrics] = useState<LiveMetricsSnapshot>({
    total_requests: 1420,
    onnx_offload_ratio: 0.814,
    avg_latency_ms: 11.2,
    cumulative_cost_saved_usd: 4.26,
    circuit_breaker_state: "CLOSED",
    queue_depth_triage: 0,
    queue_depth_shadow: 0,
    queue_depth_dlq: 0,
  });

  const [promptText, setPromptText] = useState("");
  const [isInferring, setIsInferring] = useState(false);
  const [isRetraining, setIsRetraining] = useState(false);
  const [lastResult, setLastResult] = useState<RouterInferenceResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [retrainMsg, setRetrainMsg] = useState<string | null>(null);
  const [inferenceHistory, setInferenceHistory] = useState<RouterInferenceResponse[]>([]);
  const [filterTarget, setFilterTarget] = useState<string>("ALL");

  useEffect(() => {
    // Poll metrics snapshot initially
    apiClient
      .fetchMetricsSnapshot()
      .then((data) => setMetrics(data))
      .catch((err) => console.warn("Metrics fetch error:", err));

    // Listen to live WebSocket telemetry
    const unsubMetrics = wsClient.subscribe("SYSTEM_METRICS", (data) => {
      setMetrics((prev) => ({ ...prev, ...data }));
    });

    const unsubRouter = wsClient.subscribe("ROUTER_INFERENCE", (data: RouterInferenceResponse) => {
      setInferenceHistory((prev) => [data, ...prev.slice(0, 49)]);
    });

    return () => {
      unsubMetrics();
      unsubRouter();
    };
  }, []);

  const handleInfer = async (textToRun?: string) => {
    const text = textToRun || promptText;
    if (!text.trim()) {
      setErrorMsg("Lütfen test edilecek olay metnini girin.");
      return;
    }

    setIsInferring(true);
    setErrorMsg(null);

    try {
      const resp = await apiClient.inferRouter(text);
      setLastResult(resp);
      setInferenceHistory((prev) => [resp, ...prev.slice(0, 49)]);
    } catch (err: any) {
      setErrorMsg(err.detail || err.message || "Model çıkarım hatası oluştu.");
    } finally {
      setIsInferring(false);
    }
  };

  const handleTriggerRetrain = async () => {
    setIsRetraining(true);
    setRetrainMsg(null);
    try {
      const res = await apiClient.triggerRetrain();
      setRetrainMsg(res.message || "Öğrenci modeli aktif öğrenme eğitimi tetiklendi. Hot-swap hazırlanıyor.");
    } catch (err: any) {
      setErrorMsg(err.detail || err.message || "Yeniden eğitim tetiklenemedi.");
    } finally {
      setIsRetraining(false);
    }
  };

  const filteredHistory = inferenceHistory.filter((item) => {
    if (filterTarget === "ALL") return true;
    return item.execution_target === filterTarget;
  });

  return (
    <div className="space-y-6">
      {/* Top Banner / System Status */}
      <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg gap-4">
        <div>
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-cyan-400 animate-pulse"></span>
            Model Yönlendirici (ONNX & LLM Hibrit Ağ)
          </h2>
          <p className="text-sm text-slate-400 mt-1">
            Basit ihbarlar CPU üzerinde çalışan 8-bit ONNX modeliyle milisaniyeler içinde sınıflandırılır. Belirsiz veya karmaşık olaylar ana LLM'e devredilir.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <span
            className={`px-3 py-1 rounded-full text-xs font-semibold border ${
              metrics.circuit_breaker_state === "CLOSED"
                ? "bg-emerald-950/60 text-emerald-400 border-emerald-800"
                : metrics.circuit_breaker_state === "HALF_OPEN"
                ? "bg-amber-950/60 text-amber-400 border-amber-800"
                : "bg-rose-950/60 text-rose-400 border-rose-800"
            }`}
          >
            Devre Kesici: {metrics.circuit_breaker_state === "CLOSED" ? "Normal (Kapalı)" : metrics.circuit_breaker_state === "HALF_OPEN" ? "Test (Yarı Açık)" : "Tetiklendi (Açık)"}
          </span>
          <button
            onClick={handleTriggerRetrain}
            disabled={isRetraining}
            className="px-4 py-2 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white rounded-lg text-xs font-bold transition shadow disabled:opacity-50 flex items-center gap-2"
          >
            {isRetraining ? (
              <>
                <svg className="animate-spin h-4 w-4 text-white" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                </svg>
                Distilling INT8...
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                Trigger Active Retrain
              </>
            )}
          </button>
        </div>
      </div>

      {retrainMsg && (
        <div className="bg-cyan-950/40 border border-cyan-800 text-cyan-300 px-4 py-3 rounded-lg text-sm flex items-center justify-between">
          <span>{retrainMsg}</span>
          <button onClick={() => setRetrainMsg(null)} className="text-cyan-400 font-bold hover:underline">
            ✕
          </button>
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-xl shadow">
          <div className="text-xs font-medium text-slate-400">Total Mesh Inferences</div>
          <div className="text-2xl font-black text-white mt-1">{metrics.total_requests.toLocaleString()}</div>
          <div className="text-xs text-slate-500 mt-1">Real-time edge + teacher throughput</div>
        </div>

        <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-xl shadow">
          <div className="text-xs font-medium text-slate-400">INT8 Student Offload Ratio</div>
          <div className="text-2xl font-black text-cyan-400 mt-1">
            {(metrics.onnx_offload_ratio * 100).toFixed(1)}%
          </div>
          <div className="w-full bg-slate-800 h-1.5 rounded-full mt-2 overflow-hidden">
            <div
              className="bg-cyan-500 h-1.5 rounded-full transition-all duration-500"
              style={{ width: `${Math.min(metrics.onnx_offload_ratio * 100, 100)}%` }}
            ></div>
          </div>
        </div>

        <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-xl shadow">
          <div className="text-xs font-medium text-slate-400">Mean Inference Latency</div>
          <div className="text-2xl font-black text-emerald-400 mt-1">{metrics.avg_latency_ms.toFixed(1)} ms</div>
          <div className="text-xs text-slate-500 mt-1">
            Student: ~6.4 ms | LLM: ~850 ms
          </div>
        </div>

        <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-xl shadow">
          <div className="text-xs font-medium text-slate-400">Cumulative Cost Saved</div>
          <div className="text-2xl font-black text-amber-400 mt-1">
            ${metrics.cumulative_cost_saved_usd.toFixed(2)}
          </div>
          <div className="text-xs text-slate-500 mt-1">Calculated @ $0.003 / LLM query</div>
        </div>
      </div>

      {/* Main Grid: Interactive Sandbox & Results */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Inference Sandbox */}
        <div className="lg:col-span-6 bg-slate-900 border border-slate-800 rounded-xl p-5 shadow flex flex-col space-y-4">
          <h3 className="text-base font-bold text-white flex items-center justify-between">
            <span>Routing Sandbox & Entropy Probe</span>
            <span className="text-xs font-normal text-slate-400">Test INT8 vs LLM Gate</span>
          </h3>

          <div className="flex flex-wrap gap-2">
            {PRESET_PROMPTS.map((preset, idx) => (
              <button
                key={idx}
                onClick={() => {
                  setPromptText(preset.text);
                  handleInfer(preset.text);
                }}
                className="text-xs px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition"
              >
                {preset.label}
              </button>
            ))}
          </div>

          <div className="flex-1">
            <textarea
              value={promptText}
              onChange={(e) => setPromptText(e.target.value)}
              placeholder="Giriş metnini buraya yazın (Örn: 'Elektrik direği devrildi, kıvılcım çıkıyor...')"
              rows={5}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg p-3 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500"
            />
          </div>

          {errorMsg && (
            <div className="bg-rose-950/40 border border-rose-800 text-rose-300 px-3 py-2 rounded text-xs">
              {errorMsg}
            </div>
          )}

          <div className="flex justify-end gap-3">
            <button
              onClick={() => setPromptText("")}
              className="px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs font-semibold"
            >
              Clear
            </button>
            <button
              onClick={() => handleInfer()}
              disabled={isInferring}
              className="px-5 py-2 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg text-xs font-bold transition shadow disabled:opacity-50 flex items-center gap-2"
            >
              {isInferring ? "Analyzing Vectors..." : "Infer & Route"}
            </button>
          </div>
        </div>

        {/* Right Column: Routing Decision Inspector */}
        <div className="lg:col-span-6 bg-slate-900 border border-slate-800 rounded-xl p-5 shadow flex flex-col space-y-4">
          <h3 className="text-base font-bold text-white flex items-center justify-between">
            <span>Routing Decision Engine</span>
            {lastResult && (
              <span
                className={`px-2.5 py-0.5 rounded text-xs font-bold border ${
                  lastResult.execution_target === "ONNX_STUDENT_INT8"
                    ? "bg-cyan-950 text-cyan-300 border-cyan-700"
                    : lastResult.execution_target === "SEMANTIC_CACHE"
                    ? "bg-emerald-950 text-emerald-300 border-emerald-700"
                    : "bg-purple-950 text-purple-300 border-purple-700"
                }`}
              >
                {lastResult.execution_target}
              </span>
            )}
          </h3>

          {!lastResult ? (
            <div className="flex-1 flex flex-col items-center justify-center p-8 text-center text-slate-500 border border-dashed border-slate-800 rounded-lg">
              <svg className="w-12 h-12 text-slate-700 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
              <p className="text-sm">Henüz bir çıkarım çalıştırılmadı.</p>
              <p className="text-xs text-slate-600 mt-1">Sol panelden bir senaryo seçip "Infer & Route" butonuna basın.</p>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                  <div className="text-xs text-slate-400">Classified Intent</div>
                  <div className="text-sm font-bold text-cyan-400 mt-1">{lastResult.intent}</div>
                </div>
                <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                  <div className="text-xs text-slate-400">Confidence</div>
                  <div className="text-sm font-bold text-white mt-1">
                    {(lastResult.confidence * 100).toFixed(1)}%
                  </div>
                </div>
                <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                  <div className="text-xs text-slate-400">Execution Latency</div>
                  <div className="text-sm font-bold text-emerald-400 mt-1">{lastResult.latency_ms.toFixed(1)} ms</div>
                </div>
                <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                  <div className="text-xs text-slate-400">Cost Saved</div>
                  <div className="text-sm font-bold text-amber-400 mt-1">
                    ${lastResult.cost_saved_usd.toFixed(4)}
                  </div>
                </div>
              </div>

              {/* Entropy & OOD Mathematical Bars */}
              <div className="bg-slate-950 p-4 rounded-lg border border-slate-800 space-y-3">
                <div>
                  <div className="flex justify-between text-xs text-slate-300 font-mono">
                    <span>Normalized Shannon Entropy: {lastResult.student_entropy?.toFixed(3) ?? "N/A"}</span>
                    <span>Threshold: ≤ 0.280</span>
                  </div>
                  <div className="w-full bg-slate-800 h-2 rounded-full mt-1.5 overflow-hidden">
                    <div
                      className={`h-2 rounded-full transition-all ${
                        (lastResult.student_entropy || 0) <= 0.28 ? "bg-emerald-500" : "bg-rose-500"
                      }`}
                      style={{ width: `${Math.min(((lastResult.student_entropy || 0) / 1.0) * 100, 100)}%` }}
                    ></div>
                  </div>
                </div>

                <div>
                  <div className="flex justify-between text-xs text-slate-300 font-mono">
                    <span>OOD In-Distribution Cosine Sim: {lastResult.ood_similarity?.toFixed(3) ?? "N/A"}</span>
                    <span>Threshold: ≥ 0.750</span>
                  </div>
                  <div className="w-full bg-slate-800 h-2 rounded-full mt-1.5 overflow-hidden">
                    <div
                      className={`h-2 rounded-full transition-all ${
                        (lastResult.ood_similarity || 0) >= 0.75 ? "bg-emerald-500" : "bg-amber-500"
                      }`}
                      style={{ width: `${Math.min(((lastResult.ood_similarity || 0) / 1.0) * 100, 100)}%` }}
                    ></div>
                  </div>
                </div>
              </div>

              {/* Raw JSON Debug inspector */}
              <details className="bg-slate-950 p-3 rounded-lg border border-slate-800 text-xs">
                <summary className="cursor-pointer text-slate-400 font-mono">Detailed Telemetry Payload (JSON)</summary>
                <pre className="mt-2 text-cyan-300 overflow-x-auto p-2 bg-slate-900 rounded font-mono text-[11px]">
                  {JSON.stringify(lastResult, null, 2)}
                </pre>
              </details>
            </div>
          )}
        </div>
      </div>

      {/* Historical Telemetry Stream Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow space-y-4">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <h3 className="text-base font-bold text-white flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-400"></span>
            Real-Time Decision Stream (Live Telemetry)
          </h3>
          <div className="flex items-center gap-2 text-xs">
            <span className="text-slate-400">Filter Target:</span>
            {["ALL", "ONNX_STUDENT_INT8", "TEACHER_LLM_FALLBACK", "SEMANTIC_CACHE"].map((target) => (
              <button
                key={target}
                onClick={() => setFilterTarget(target)}
                className={`px-2 py-1 rounded border transition ${
                  filterTarget === target
                    ? "bg-cyan-900/60 text-cyan-300 border-cyan-600 font-bold"
                    : "bg-slate-800 text-slate-400 border-slate-700 hover:text-white"
                }`}
              >
                {target.replace("_FALLBACK", "").replace("_INT8", "")}
              </button>
            ))}
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-slate-300 border-collapse">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400">
                <th className="py-2.5 px-3">Request ID</th>
                <th className="py-2.5 px-3">Target</th>
                <th className="py-2.5 px-3">Predicted Intent</th>
                <th className="py-2.5 px-3">Confidence</th>
                <th className="py-2.5 px-3">Shannon Entropy</th>
                <th className="py-2.5 px-3">Latency</th>
                <th className="py-2.5 px-3">Cost Saved</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-mono">
              {filteredHistory.length === 0 ? (
                <tr>
                  <td colSpan={7} className="text-center py-6 text-slate-500">
                    Henüz telemetri akışı kaydedilmedi. Yukarıdan çıkarım testi yapın.
                  </td>
                </tr>
              ) : (
                filteredHistory.map((item, idx) => (
                  <tr key={idx} className="hover:bg-slate-800/40">
                    <td className="py-2.5 px-3 text-slate-400">{item.request_id?.slice(0, 12)}...</td>
                    <td className="py-2.5 px-3">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          item.execution_target === "ONNX_STUDENT_INT8"
                            ? "bg-cyan-950 text-cyan-300"
                            : item.execution_target === "SEMANTIC_CACHE"
                            ? "bg-emerald-950 text-emerald-300"
                            : "bg-purple-950 text-purple-300"
                        }`}
                      >
                        {item.execution_target}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 font-sans font-semibold text-white">{item.intent}</td>
                    <td className="py-2.5 px-3">{(item.confidence * 100).toFixed(1)}%</td>
                    <td className="py-2.5 px-3 text-slate-400">{item.student_entropy?.toFixed(3) ?? "-"}</td>
                    <td className="py-2.5 px-3 text-emerald-400">{item.latency_ms.toFixed(1)} ms</td>
                    <td className="py-2.5 px-3 text-amber-400">${item.cost_saved_usd.toFixed(4)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
