import React, { useState } from "react";
import { RefreshCw } from "lucide-react";

export const ByzantineMeshDashboardView: React.FC = () => {
  const [roundNumber, setRoundNumber] = useState(14);
  const [runningRound, setRunningRound] = useState(false);
  const [prunedNodes] = useState<string[]>(["worker-node-03-ist", "worker-node-07-ank"]);
  const [accumulatedEpsilon, setAccumulatedEpsilon] = useState(1.42);

  const handleTriggerRound = () => {
    setRunningRound(true);
    setTimeout(() => {
      setRoundNumber((r) => r + 1);
      setAccumulatedEpsilon((e) => Math.min(5.0, e + 0.12));
      setRunningRound(false);
    }, 600);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem", maxWidth: "1600px", margin: "0 auto", width: "100%" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.25rem" }}>
            <span className="status-dot status-dot-active" />
            <h1 style={{ fontSize: "1.45rem", fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.01em", margin: 0 }}>
              Byzantine Federated Mesh Consensus
            </h1>
          </div>
          <p style={{ color: "var(--text-tertiary)", fontSize: "0.85rem", margin: 0 }}>
            Distributed Multi-Krum Euclidean distance outlier pruning with Rényi Differential Privacy (RDP) budget accounting.
          </p>
        </div>

        <button onClick={handleTriggerRound} className="btn-primary" disabled={runningRound} style={{ fontSize: "0.82rem" }}>
          <RefreshCw size={14} className={runningRound ? "animate-spin" : ""} />
          {runningRound ? "Aggregating Gradients..." : "Trigger Federated Round"}
        </button>
      </div>

      {/* KPI Cards */}
      <div className="grid-responsive-kpi">
        <div className="metric-card">
          <div className="metric-label">Active Federated Round</div>
          <div className="metric-value" style={{ color: "var(--brand-primary)" }}>#{roundNumber}</div>
          <div className="metric-subtext">Global Model v2.4</div>
        </div>

        <div className="metric-card">
          <div className="metric-label">Participating Workers</div>
          <div className="metric-value">8 Nodes</div>
          <div className="metric-subtext">Multi-Krum m=8, f=2</div>
        </div>

        <div className="metric-card">
          <div className="metric-label">Byzantine Pruned</div>
          <div className="metric-value" style={{ color: "var(--color-danger)" }}>{prunedNodes.length} Nodes</div>
          <div className="metric-subtext">Euclidean Outliers</div>
        </div>

        <div className="metric-card">
          <div className="metric-label">Rényi DP Budget (ε)</div>
          <div className="metric-value" style={{ color: "var(--color-warning)" }}>{accumulatedEpsilon.toFixed(2)} / 5.0</div>
          <div className="metric-subtext">α=4.0, δ=1e-5</div>
        </div>
      </div>

      {/* Worker Consensus Grid */}
      <div className="panel-card" style={{ padding: "1.25rem" }}>
        <div style={{ borderBottom: "1px solid var(--border-subtle)", paddingBottom: "0.75rem", marginBottom: "1rem" }}>
          <h3 style={{ fontSize: "0.85rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em", color: "var(--text-secondary)", margin: 0 }}>
            Edge Node Gradient Consensus Table
          </h3>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
          {[
            { id: "worker-node-01-ist", score: 0.124, status: "HONEST_CONSENSUS" },
            { id: "worker-node-02-ist", score: 0.142, status: "HONEST_CONSENSUS" },
            { id: "worker-node-03-ist", score: 8.942, status: "BYZANTINE_PRUNED" },
            { id: "worker-node-04-izm", score: 0.118, status: "HONEST_CONSENSUS" },
            { id: "worker-node-05-izm", score: 0.135, status: "HONEST_CONSENSUS" },
            { id: "worker-node-06-ank", score: 0.165, status: "HONEST_CONSENSUS" },
            { id: "worker-node-07-ank", score: 9.871, status: "BYZANTINE_PRUNED" },
            { id: "worker-node-08-ant", score: 0.128, status: "HONEST_CONSENSUS" },
          ].map((node) => {
            const isByz = node.status === "BYZANTINE_PRUNED";
            return (
              <div
                key={node.id}
                className="panel-elevated"
                style={{
                  padding: "0.75rem 1rem",
                  borderRadius: "var(--radius-sm)",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  flexWrap: "wrap",
                  gap: "0.5rem",
                  borderLeft: `3px solid ${isByz ? "var(--color-danger)" : "var(--color-success)"}`,
                }}
              >
                <div>
                  <div style={{ fontWeight: 600, fontSize: "0.85rem", color: "var(--text-primary)" }}>
                    {node.id}
                  </div>
                  <div style={{ fontSize: "0.72rem", color: "var(--text-tertiary)", marginTop: "0.15rem" }}>
                    Multi-Krum Neighbor Sum Score: <code style={{ fontFamily: "var(--font-mono)", color: "var(--text-secondary)" }}>{node.score.toFixed(3)}</code>
                  </div>
                </div>

                <div>
                  <span className={`badge-solid ${isByz ? "badge-critical" : "badge-success"}`} style={{ fontSize: "0.68rem" }}>
                    {node.status}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export default ByzantineMeshDashboardView;
