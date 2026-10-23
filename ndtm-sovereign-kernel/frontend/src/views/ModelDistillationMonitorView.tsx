import React, { useState } from "react";
import { Zap } from "lucide-react";

export const ModelDistillationMonitorView: React.FC = () => {
  const [activeSlot, setActiveSlot] = useState<"SLOT_A" | "SLOT_B">("SLOT_A");
  const [loraVersion, setLoraVersion] = useState("v2.1.0-istanbul-retrained");
  const [swapping, setSwapping] = useState(false);
  const [swapMessage, setSwapMessage] = useState<string | null>(null);

  const handleHotSwap = () => {
    setSwapping(true);
    setTimeout(() => {
      const nextSlot = activeSlot === "SLOT_A" ? "SLOT_B" : "SLOT_A";
      setActiveSlot(nextSlot);
      setLoraVersion(`v2.1.${Math.floor(Math.random() * 90 + 10)}-active`);
      setSwapping(false);
      setSwapMessage(`Atomic zero-downtime hot-swap committed to ${nextSlot} (Rank 16, Alpha 32.0).`);
    }, 400);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem", maxWidth: "1600px", margin: "0 auto", width: "100%" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.25rem" }}>
            <span className="status-dot status-dot-active" />
            <h1 style={{ fontSize: "1.45rem", fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.01em", margin: 0 }}>
              Knowledge Distillation & Model Forge Monitor
            </h1>
          </div>
          <p style={{ color: "var(--text-tertiary)", fontSize: "0.85rem", margin: 0 }}>
            Synthetic teacher data curation, tri-loss distillation (Task + Scaled KL + InfoNCE), and double-buffered LoRA hot-swapping.
          </p>
        </div>

        <button onClick={handleHotSwap} className="btn-primary" disabled={swapping} style={{ fontSize: "0.82rem" }}>
          <Zap size={14} />
          {swapping ? "Switching Atomic Pointer..." : "Hot-Swap Active LoRA"}
        </button>
      </div>

      {swapMessage && (
        <div style={{ padding: "0.75rem 1rem", background: "rgba(5, 150, 105, 0.08)", border: "1px solid rgba(5, 150, 105, 0.3)", borderRadius: "var(--radius-sm)", color: "var(--color-success)", fontSize: "0.82rem" }}>
          {swapMessage}
        </div>
      )}

      {/* Responsive KPI Grid */}
      <div className="grid-responsive-kpi">
        <div className="metric-card">
          <div className="metric-label">Combined Distillation Loss</div>
          <div className="metric-value" style={{ color: "var(--brand-primary)" }}>0.2841</div>
          <div className="metric-subtext" style={{ color: "var(--color-success)" }}>-12.4% vs baseline</div>
        </div>

        <div className="metric-card">
          <div className="metric-label">Temperature-Scaled KL (T=3.0)</div>
          <div className="metric-value" style={{ color: "var(--color-warning)" }}>0.0892</div>
          <div className="metric-subtext">T² · KL(Ps || Pt)</div>
        </div>

        <div className="metric-card">
          <div className="metric-label">InfoNCE Contrastive Sim</div>
          <div className="metric-value" style={{ color: "var(--color-success)" }}>0.964</div>
          <div className="metric-subtext">Cosine Alignment</div>
        </div>

        <div className="metric-card">
          <div className="metric-label">INT8 Compression Gain</div>
          <div className="metric-value">3.94x</div>
          <div className="metric-subtext">Symmetric Quantized</div>
        </div>
      </div>

      {/* Double Buffered LoRA Status */}
      <div className="panel-card" style={{ padding: "1.25rem" }}>
        <div style={{ borderBottom: "1px solid var(--border-subtle)", paddingBottom: "0.75rem", marginBottom: "1rem" }}>
          <h3 style={{ fontSize: "0.85rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em", color: "var(--text-secondary)", margin: 0 }}>
            Double-Buffered LoRA Adapter Status
          </h3>
        </div>

        <div className="grid-responsive-2">
          <div
            className="panel-elevated"
            style={{
              padding: "1rem 1.2rem",
              borderRadius: "var(--radius-sm)",
              border: activeSlot === "SLOT_A" ? "1px solid var(--brand-primary)" : "1px solid var(--border-subtle)",
              background: activeSlot === "SLOT_A" ? "var(--bg-surface-elevated)" : undefined,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.4rem" }}>
              <span style={{ fontWeight: 700, color: "var(--text-primary)", fontSize: "0.9rem" }}>Buffer Slot A</span>
              <span className={`badge-solid ${activeSlot === "SLOT_A" ? "badge-success" : "badge-medium"}`} style={{ fontSize: "0.68rem" }}>
                {activeSlot === "SLOT_A" ? "ACTIVE SERVING" : "STANDBY"}
              </span>
            </div>
            <div style={{ fontSize: "0.78rem", color: "var(--text-tertiary)" }}>
              Version: <code style={{ fontFamily: "var(--font-mono)", color: "var(--text-secondary)" }}>{activeSlot === "SLOT_A" ? loraVersion : "v2.0.8-cached"}</code> • Rank: 16 • Alpha: 32.0
            </div>
          </div>

          <div
            className="panel-elevated"
            style={{
              padding: "1rem 1.2rem",
              borderRadius: "var(--radius-sm)",
              border: activeSlot === "SLOT_B" ? "1px solid var(--brand-primary)" : "1px solid var(--border-subtle)",
              background: activeSlot === "SLOT_B" ? "var(--bg-surface-elevated)" : undefined,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.4rem" }}>
              <span style={{ fontWeight: 700, color: "var(--text-primary)", fontSize: "0.9rem" }}>Buffer Slot B</span>
              <span className={`badge-solid ${activeSlot === "SLOT_B" ? "badge-success" : "badge-medium"}`} style={{ fontSize: "0.68rem" }}>
                {activeSlot === "SLOT_B" ? "ACTIVE SERVING" : "STANDBY"}
              </span>
            </div>
            <div style={{ fontSize: "0.78rem", color: "var(--text-tertiary)" }}>
              Version: <code style={{ fontFamily: "var(--font-mono)", color: "var(--text-secondary)" }}>{activeSlot === "SLOT_B" ? loraVersion : "v2.0.9-staged"}</code> • Rank: 16 • Alpha: 32.0
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ModelDistillationMonitorView;
